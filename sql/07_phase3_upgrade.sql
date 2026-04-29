-- ============================================================
-- 急诊科 EDC 系统 - 第三阶段升级
-- 功能: 绿色通道专项、抢救时间轴、质控运营视图
-- 执行前提: 已执行 01~06 脚本
-- ============================================================

USE ed_emergency;

-- ============================================================
-- 1. 安全追加列
-- ============================================================

DROP PROCEDURE IF EXISTS sp_add_column_if_missing;
DELIMITER //
CREATE PROCEDURE sp_add_column_if_missing(
    IN p_table_name VARCHAR(64),
    IN p_column_name VARCHAR(64),
    IN p_column_definition TEXT
)
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = p_table_name
          AND COLUMN_NAME = p_column_name
    ) THEN
        SET @ddl = CONCAT('ALTER TABLE `', p_table_name, '` ADD COLUMN ', p_column_definition);
        PREPARE stmt FROM @ddl;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END IF;
END //
DELIMITER ;

CALL sp_add_column_if_missing('ed_green_channel', 'channel_status', '`channel_status` VARCHAR(20) DEFAULT ''进行中'' COMMENT ''状态(进行中/已完成/已关闭)'' AFTER `channel_outcome`');
CALL sp_add_column_if_missing('ed_green_channel', 'completed_time', '`completed_time` DATETIME DEFAULT NULL COMMENT ''完成时间'' AFTER `channel_status`');
CALL sp_add_column_if_missing('ed_green_channel', 'coordinator_nurse_id', '`coordinator_nurse_id` BIGINT DEFAULT NULL COMMENT ''协调护士ID'' AFTER `activate_doctor`');
CALL sp_add_column_if_missing('ed_green_channel', 'latest_event_time', '`latest_event_time` DATETIME DEFAULT NULL COMMENT ''最近节点时间'' AFTER `coordinator_nurse_id`');

CALL sp_add_column_if_missing('ed_rescue_record', 'rescue_status', '`rescue_status` VARCHAR(20) DEFAULT ''抢救中'' COMMENT ''状态(抢救中/已完成)'' AFTER `outcome`');
CALL sp_add_column_if_missing('ed_rescue_record', 'latest_event_time', '`latest_event_time` DATETIME DEFAULT NULL COMMENT ''最近抢救节点时间'' AFTER `rescue_status`');
CALL sp_add_column_if_missing('ed_rescue_record', 'rosc_time', '`rosc_time` DATETIME DEFAULT NULL COMMENT ''自主循环恢复时间'' AFTER `cpr_duration`');

DROP PROCEDURE IF EXISTS sp_add_column_if_missing;

-- ============================================================
-- 2. 绿色通道事件 / 抢救时间轴
-- ============================================================

CREATE TABLE IF NOT EXISTS ed_green_channel_event (
    event_id             BIGINT          NOT NULL AUTO_INCREMENT,
    channel_id           BIGINT          NOT NULL,
    visit_id             BIGINT          NOT NULL,
    event_type           VARCHAR(40)     NOT NULL COMMENT 'activate/ecg/ct/needle/balloon/surgery/admission/handoff/close',
    event_name           VARCHAR(100)    NOT NULL,
    event_time           DATETIME        NOT NULL,
    elapsed_seconds      INT             DEFAULT NULL,
    recorder_id          BIGINT          DEFAULT NULL,
    note                 VARCHAR(500)    DEFAULT NULL,
    created_at           DATETIME        DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (event_id),
    KEY idx_channel (channel_id),
    KEY idx_visit (visit_id),
    KEY idx_event_time (event_time),
    KEY idx_event_type (event_type)
) ENGINE=InnoDB COMMENT='绿色通道节点事件表';

CREATE TABLE IF NOT EXISTS ed_rescue_timeline (
    timeline_id          BIGINT          NOT NULL AUTO_INCREMENT,
    rescue_id            BIGINT          NOT NULL,
    visit_id             BIGINT          NOT NULL,
    event_time           DATETIME        NOT NULL,
    event_type           VARCHAR(40)     NOT NULL COMMENT 'start/cpr/defibrillation/intubation/medication/rosc/transfer/end/other',
    event_name           VARCHAR(100)    NOT NULL,
    performer_id         BIGINT          DEFAULT NULL,
    medication_name      VARCHAR(100)    DEFAULT NULL,
    dose                 VARCHAR(50)     DEFAULT NULL,
    route                VARCHAR(30)     DEFAULT NULL,
    note                 VARCHAR(500)    DEFAULT NULL,
    vital_snapshot       JSON            DEFAULT NULL,
    created_at           DATETIME        DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (timeline_id),
    KEY idx_rescue (rescue_id),
    KEY idx_visit (visit_id),
    KEY idx_event_time (event_time),
    KEY idx_event_type (event_type)
) ENGINE=InnoDB COMMENT='抢救时间轴事件表';

-- ============================================================
-- 3. 工作流与质控视图
-- ============================================================

CREATE OR REPLACE VIEW v_green_channel_active AS
SELECT
    gc.channel_id,
    gc.visit_id,
    gc.channel_type,
    gc.activate_time,
    gc.activate_doctor,
    gc.coordinator_nurse_id,
    gc.latest_event_time,
    gc.door_to_ecg,
    gc.door_to_needle,
    gc.door_to_balloon,
    gc.door_to_ct,
    gc.door_to_surgery,
    gc.target_met,
    gc.channel_outcome,
    gc.channel_status,
    gc.completed_time,
    v.visit_no,
    v.triage_level,
    v.triage_color,
    v.visit_status,
    v.chief_complaint,
    p.patient_name,
    p.gender,
    p.age,
    p.age_unit,
    b.bed_code,
    sd.staff_name AS activate_doctor_name,
    sn.staff_name AS coordinator_nurse_name,
    (
        SELECT COUNT(*)
        FROM ed_green_channel_event e
        WHERE e.channel_id = gc.channel_id
    ) AS event_count,
    (
        SELECT e.event_name
        FROM ed_green_channel_event e
        WHERE e.channel_id = gc.channel_id
        ORDER BY e.event_time DESC, e.event_id DESC
        LIMIT 1
    ) AS latest_event_name,
    TIMESTAMPDIFF(MINUTE, gc.activate_time, IFNULL(gc.completed_time, NOW())) AS channel_minutes
FROM ed_green_channel gc
JOIN ed_visit v ON gc.visit_id = v.visit_id
JOIN patient_info p ON v.patient_id = p.patient_id
LEFT JOIN ed_bed b ON v.bed_id = b.bed_id
LEFT JOIN sys_staff sd ON gc.activate_doctor = sd.staff_id
LEFT JOIN sys_staff sn ON gc.coordinator_nurse_id = sn.staff_id
WHERE gc.channel_status = '进行中'
ORDER BY gc.activate_time DESC;

CREATE OR REPLACE VIEW v_green_channel_dashboard AS
SELECT
    (SELECT COUNT(*) FROM ed_green_channel WHERE DATE(activate_time) = CURDATE()) AS today_channel_count,
    (SELECT COUNT(*) FROM ed_green_channel WHERE channel_status = '进行中') AS active_channel_count,
    (SELECT COUNT(*) FROM ed_green_channel WHERE DATE(IFNULL(completed_time, activate_time)) = CURDATE() AND channel_status = '已完成') AS completed_today_count,
    (SELECT COUNT(*) FROM ed_green_channel WHERE DATE(IFNULL(completed_time, activate_time)) = CURDATE() AND target_met = 1) AS target_met_today_count,
    (
        SELECT ROUND(
            AVG(CASE WHEN target_met IS NOT NULL THEN target_met * 100 ELSE NULL END),
            1
        )
        FROM ed_green_channel
        WHERE DATE(IFNULL(completed_time, activate_time)) = CURDATE()
    ) AS target_met_rate,
    (
        SELECT ROUND(AVG(door_to_ecg) / 60, 1)
        FROM ed_green_channel
        WHERE DATE(activate_time) = CURDATE() AND door_to_ecg IS NOT NULL
    ) AS avg_door_to_ecg_min,
    (
        SELECT ROUND(AVG(door_to_ct) / 60, 1)
        FROM ed_green_channel
        WHERE DATE(activate_time) = CURDATE() AND door_to_ct IS NOT NULL
    ) AS avg_door_to_ct_min,
    (
        SELECT ROUND(AVG(door_to_balloon) / 60, 1)
        FROM ed_green_channel
        WHERE DATE(activate_time) = CURDATE() AND door_to_balloon IS NOT NULL
    ) AS avg_door_to_balloon_min,
    (
        SELECT ROUND(AVG(door_to_needle) / 60, 1)
        FROM ed_green_channel
        WHERE DATE(activate_time) = CURDATE() AND door_to_needle IS NOT NULL
    ) AS avg_door_to_needle_min;

CREATE OR REPLACE VIEW v_rescue_worklist AS
SELECT
    r.rescue_id,
    r.visit_id,
    r.rescue_start,
    r.rescue_end,
    r.rescue_duration,
    r.rescue_leader,
    r.arrest_type,
    r.cpr_flag,
    r.cpr_start,
    r.cpr_duration,
    r.rosc_time,
    r.airway_type,
    r.outcome,
    r.rescue_status,
    r.latest_event_time,
    r.rescue_summary,
    v.visit_no,
    v.triage_level,
    v.triage_color,
    v.visit_status,
    v.chief_complaint,
    p.patient_name,
    p.gender,
    p.age,
    p.age_unit,
    b.bed_code,
    s.staff_name AS rescue_leader_name,
    (
        SELECT COUNT(*)
        FROM ed_rescue_timeline t
        WHERE t.rescue_id = r.rescue_id
    ) AS event_count,
    (
        SELECT t.event_name
        FROM ed_rescue_timeline t
        WHERE t.rescue_id = r.rescue_id
        ORDER BY t.event_time DESC, t.timeline_id DESC
        LIMIT 1
    ) AS latest_event_name
FROM ed_rescue_record r
JOIN ed_visit v ON r.visit_id = v.visit_id
JOIN patient_info p ON v.patient_id = p.patient_id
LEFT JOIN ed_bed b ON v.bed_id = b.bed_id
LEFT JOIN sys_staff s ON r.rescue_leader = s.staff_id
ORDER BY CASE r.rescue_status WHEN '抢救中' THEN 0 ELSE 1 END, r.rescue_start DESC;

CREATE OR REPLACE VIEW v_demo_data_scale AS
SELECT
    (SELECT COUNT(*) FROM patient_info) AS patient_count,
    (SELECT COUNT(*) FROM ed_visit) AS visit_count,
    (SELECT COUNT(*) FROM ed_visit WHERE visit_status NOT IN ('已离院', '已转院', '死亡')) AS active_visit_count,
    (SELECT COUNT(*) FROM ed_order) AS order_count,
    (SELECT COUNT(*) FROM ed_lab_order) AS lab_count,
    (SELECT COUNT(*) FROM ed_imaging_order) AS imaging_count,
    (SELECT COUNT(*) FROM ed_nursing_record) AS nursing_count,
    (SELECT COUNT(*) FROM ed_green_channel) AS green_channel_count,
    (SELECT COUNT(*) FROM ed_green_channel_event) AS green_event_count,
    (SELECT COUNT(*) FROM ed_rescue_record) AS rescue_count,
    (SELECT COUNT(*) FROM ed_rescue_timeline) AS rescue_event_count,
    (SELECT COUNT(*) FROM ed_observation) AS observation_count,
    (SELECT COUNT(*) FROM ed_consultation) AS consultation_count,
    (SELECT COUNT(*) FROM ed_critical_value) AS critical_value_count;

CREATE OR REPLACE VIEW v_quality_dashboard AS
SELECT
    (SELECT COUNT(*) FROM ed_visit WHERE visit_date = CURDATE()) AS today_visits,
    (SELECT COUNT(*) FROM ed_visit WHERE visit_status NOT IN ('已离院', '已转院', '死亡')) AS active_visits,
    (SELECT COUNT(*) FROM ed_visit WHERE visit_status = '候诊') AS waiting_count,
    (
        SELECT COUNT(*)
        FROM ed_visit
        WHERE visit_status = '候诊'
          AND TIMESTAMPDIFF(MINUTE, visit_time, NOW()) >= 30
    ) AS waiting_over_30min,
    (
        SELECT ROUND(AVG(TIMESTAMPDIFF(MINUTE, visit_time, IFNULL(outcome_time, NOW()))), 1)
        FROM ed_visit
        WHERE visit_status NOT IN ('分诊中')
    ) AS avg_stay_minutes,
    (
        SELECT ROUND(SUM(CASE WHEN bed_status = '占用' THEN 1 ELSE 0 END) / COUNT(*) * 100, 1)
        FROM ed_bed
    ) AS bed_occupancy_rate,
    (SELECT COUNT(*) FROM ed_green_channel WHERE channel_status = '进行中') AS green_active_count,
    (SELECT today_channel_count FROM v_green_channel_dashboard) AS green_today_count,
    (SELECT target_met_rate FROM v_green_channel_dashboard) AS green_target_met_rate,
    (SELECT COUNT(*) FROM ed_rescue_record WHERE rescue_status = '抢救中') AS rescue_active_count,
    (SELECT COUNT(*) FROM ed_rescue_record WHERE DATE(rescue_start) = CURDATE()) AS rescue_today_count,
    (SELECT COUNT(*) FROM ed_observation WHERE obs_status IN ('观察中', '待入院')) AS observation_active_count,
    (SELECT COUNT(*) FROM ed_consultation WHERE consult_status IN ('待响应', '进行中')) AS consult_pending_count,
    (SELECT COUNT(*) FROM ed_critical_value WHERE status <> '已处理') AS critical_unhandled_count,
    (
        SELECT ROUND(AVG(TIMESTAMPDIFF(MINUTE, order_time, report_time)), 1)
        FROM ed_lab_order
        WHERE DATE(order_time) = CURDATE() AND report_time IS NOT NULL
    ) AS lab_avg_tat_min,
    (
        SELECT ROUND(AVG(TIMESTAMPDIFF(MINUTE, order_time, report_time)), 1)
        FROM ed_imaging_order
        WHERE DATE(order_time) = CURDATE() AND report_time IS NOT NULL
    ) AS imaging_avg_tat_min,
    (
        SELECT ROUND(AVG(TIMESTAMPDIFF(MINUTE, notify_time, acknowledged_at)), 1)
        FROM ed_critical_value
        WHERE DATE(created_at) = CURDATE() AND notify_time IS NOT NULL AND acknowledged_at IS NOT NULL
    ) AS critical_ack_avg_min,
    (
        SELECT ROUND(AVG(CASE WHEN outcome = '住院' THEN 1 ELSE 0 END) * 100, 1)
        FROM ed_visit
        WHERE visit_date = CURDATE()
    ) AS admission_rate,
    (
        SELECT ROUND(AVG(CASE WHEN outcome = '离院回家' THEN 1 ELSE 0 END) * 100, 1)
        FROM ed_visit
        WHERE visit_date = CURDATE()
    ) AS discharge_home_rate;

-- ============================================================
-- 4. 性能索引
-- ============================================================

DROP PROCEDURE IF EXISTS sp_create_index_if_missing;
DELIMITER //
CREATE PROCEDURE sp_create_index_if_missing(
    IN p_table_name VARCHAR(64),
    IN p_index_name VARCHAR(64),
    IN p_index_sql TEXT
)
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = p_table_name
          AND INDEX_NAME = p_index_name
    ) THEN
        SET @ddl = p_index_sql;
        PREPARE stmt FROM @ddl;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END IF;
END //
DELIMITER ;

CALL sp_create_index_if_missing('ed_green_channel', 'idx_green_status_time', 'CREATE INDEX idx_green_status_time ON ed_green_channel (channel_status, activate_time)');
CALL sp_create_index_if_missing('ed_green_channel', 'idx_green_latest_event', 'CREATE INDEX idx_green_latest_event ON ed_green_channel (latest_event_time)');
CALL sp_create_index_if_missing('ed_rescue_record', 'idx_rescue_status_time', 'CREATE INDEX idx_rescue_status_time ON ed_rescue_record (rescue_status, rescue_start)');
CALL sp_create_index_if_missing('ed_rescue_record', 'idx_rescue_latest_event', 'CREATE INDEX idx_rescue_latest_event ON ed_rescue_record (latest_event_time)');

DROP PROCEDURE IF EXISTS sp_create_index_if_missing;

-- ============================================================
-- 5. 初始化节点事件
-- ============================================================

INSERT INTO ed_green_channel_event (channel_id, visit_id, event_type, event_name, event_time, elapsed_seconds, recorder_id, note)
SELECT
    gc.channel_id,
    gc.visit_id,
    'activate',
    CONCAT(gc.channel_type, '绿色通道启动'),
    gc.activate_time,
    0,
    gc.activate_doctor,
    '系统升级补充初始节点'
FROM ed_green_channel gc
WHERE NOT EXISTS (
    SELECT 1
    FROM ed_green_channel_event e
    WHERE e.channel_id = gc.channel_id
);

INSERT INTO ed_green_channel_event (channel_id, visit_id, event_type, event_name, event_time, elapsed_seconds, recorder_id, note)
SELECT
    gc.channel_id,
    gc.visit_id,
    'ecg',
    '心电图完成',
    DATE_ADD(gc.activate_time, INTERVAL gc.door_to_ecg SECOND),
    gc.door_to_ecg,
    gc.activate_doctor,
    '历史数据回填'
FROM ed_green_channel gc
WHERE gc.door_to_ecg IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM ed_green_channel_event e
      WHERE e.channel_id = gc.channel_id
        AND e.event_type = 'ecg'
  );

INSERT INTO ed_green_channel_event (channel_id, visit_id, event_type, event_name, event_time, elapsed_seconds, recorder_id, note)
SELECT
    gc.channel_id,
    gc.visit_id,
    'ct',
    'CT完成',
    DATE_ADD(gc.activate_time, INTERVAL gc.door_to_ct SECOND),
    gc.door_to_ct,
    gc.activate_doctor,
    '历史数据回填'
FROM ed_green_channel gc
WHERE gc.door_to_ct IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM ed_green_channel_event e
      WHERE e.channel_id = gc.channel_id
        AND e.event_type = 'ct'
  );

INSERT INTO ed_green_channel_event (channel_id, visit_id, event_type, event_name, event_time, elapsed_seconds, recorder_id, note)
SELECT
    gc.channel_id,
    gc.visit_id,
    'needle',
    '溶栓完成',
    DATE_ADD(gc.activate_time, INTERVAL gc.door_to_needle SECOND),
    gc.door_to_needle,
    gc.activate_doctor,
    '历史数据回填'
FROM ed_green_channel gc
WHERE gc.door_to_needle IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM ed_green_channel_event e
      WHERE e.channel_id = gc.channel_id
        AND e.event_type = 'needle'
  );

INSERT INTO ed_green_channel_event (channel_id, visit_id, event_type, event_name, event_time, elapsed_seconds, recorder_id, note)
SELECT
    gc.channel_id,
    gc.visit_id,
    'balloon',
    '球囊开通',
    DATE_ADD(gc.activate_time, INTERVAL gc.door_to_balloon SECOND),
    gc.door_to_balloon,
    gc.activate_doctor,
    '历史数据回填'
FROM ed_green_channel gc
WHERE gc.door_to_balloon IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM ed_green_channel_event e
      WHERE e.channel_id = gc.channel_id
        AND e.event_type = 'balloon'
  );

UPDATE ed_green_channel gc
SET latest_event_time = (
        SELECT MAX(e.event_time)
        FROM ed_green_channel_event e
        WHERE e.channel_id = gc.channel_id
    )
WHERE latest_event_time IS NULL;

INSERT INTO ed_rescue_record (
    visit_id, rescue_start, rescue_end, rescue_duration, rescue_leader,
    rescue_team, arrest_type, cpr_flag, cpr_start, cpr_duration, rosc_time,
    airway_type, outcome, rescue_status, latest_event_time, rescue_summary
)
SELECT
    v.visit_id,
    DATE_ADD(v.visit_time, INTERVAL 15 MINUTE),
    DATE_ADD(v.visit_time, INTERVAL 65 MINUTE),
    50,
    COALESCE(v.attending_doctor_id, 1),
    JSON_ARRAY(COALESCE(v.attending_doctor_id, 1), 7, 8),
    NULL,
    0,
    NULL,
    NULL,
    NULL,
    '无创通气',
    '成功',
    '已完成',
    DATE_ADD(v.visit_time, INTERVAL 62 MINUTE),
    '升级脚本补充示例抢救过程，用于第三阶段界面展示。'
FROM ed_visit v
WHERE v.visit_id = 4
  AND NOT EXISTS (
      SELECT 1 FROM ed_rescue_record r WHERE r.visit_id = v.visit_id
  );

INSERT INTO ed_rescue_timeline (
    rescue_id, visit_id, event_time, event_type, event_name, performer_id, note
)
SELECT
    r.rescue_id,
    r.visit_id,
    r.rescue_start,
    'start',
    '抢救启动',
    r.rescue_leader,
    '抢救小组到位'
FROM ed_rescue_record r
WHERE r.visit_id = 4
  AND NOT EXISTS (
      SELECT 1 FROM ed_rescue_timeline t WHERE t.rescue_id = r.rescue_id
  );

INSERT INTO ed_rescue_timeline (
    rescue_id, visit_id, event_time, event_type, event_name, performer_id, note
)
SELECT
    r.rescue_id,
    r.visit_id,
    DATE_ADD(r.rescue_start, INTERVAL 8 MINUTE),
    'medication',
    '甲泼尼龙静推',
    r.rescue_leader,
    '急性加重期静脉激素治疗'
FROM ed_rescue_record r
WHERE r.visit_id = 4
  AND NOT EXISTS (
      SELECT 1 FROM ed_rescue_timeline t WHERE t.rescue_id = r.rescue_id AND t.event_name = '甲泼尼龙静推'
  );

INSERT INTO ed_rescue_timeline (
    rescue_id, visit_id, event_time, event_type, event_name, performer_id, note
)
SELECT
    r.rescue_id,
    r.visit_id,
    DATE_ADD(r.rescue_start, INTERVAL 18 MINUTE),
    'other',
    '无创通气建立',
    7,
    'FiO2 40%，持续监护'
FROM ed_rescue_record r
WHERE r.visit_id = 4
  AND NOT EXISTS (
      SELECT 1 FROM ed_rescue_timeline t WHERE t.rescue_id = r.rescue_id AND t.event_name = '无创通气建立'
  );

INSERT INTO ed_rescue_timeline (
    rescue_id, visit_id, event_time, event_type, event_name, performer_id, note
)
SELECT
    r.rescue_id,
    r.visit_id,
    r.rescue_end,
    'end',
    '抢救结束',
    r.rescue_leader,
    '血氧改善，转入持续观察'
FROM ed_rescue_record r
WHERE r.visit_id = 4
  AND NOT EXISTS (
      SELECT 1 FROM ed_rescue_timeline t WHERE t.rescue_id = r.rescue_id AND t.event_type = 'end'
  );

UPDATE ed_rescue_record r
SET latest_event_time = (
        SELECT MAX(t.event_time)
        FROM ed_rescue_timeline t
        WHERE t.rescue_id = r.rescue_id
    )
WHERE latest_event_time IS NULL;
