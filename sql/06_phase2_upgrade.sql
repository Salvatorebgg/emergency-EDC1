-- ============================================================
-- 急诊科 EDC 系统 - 第二阶段闭环升级
-- 功能: 检验闭环、危急值、影像闭环、药学校验、会诊、留观转归
-- 执行前提: 已执行 01~05 脚本
-- ============================================================

USE ed_emergency;

-- ============================================================
-- 1. 补充演示账号: 检验 / 影像
-- ============================================================

INSERT INTO sys_staff (staff_code, staff_name, gender, title, dept_id, role_type, phone)
SELECT 'L001', '检验技师', 'F', '主管技师', 17, '检验', '13800004001'
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM sys_staff WHERE staff_code='L001');

INSERT INTO sys_staff (staff_code, staff_name, gender, title, dept_id, role_type, phone)
SELECT 'R001', '影像医师', 'M', '主治医师', 16, '影像', '13800004002'
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM sys_staff WHERE staff_code='R001');

INSERT INTO sys_user (username, password_hash, role_code, staff_id)
SELECT 'lab', '8d969eef6ecad3c29a3a629280e686cf0c3f5d5a86aff3ca12020c923adc6c92', 'lab', staff_id
FROM sys_staff WHERE staff_code='L001' LIMIT 1
ON DUPLICATE KEY UPDATE role_code=VALUES(role_code), staff_id=VALUES(staff_id), is_active=1;

INSERT INTO sys_user (username, password_hash, role_code, staff_id)
SELECT 'imaging', '8d969eef6ecad3c29a3a629280e686cf0c3f5d5a86aff3ca12020c923adc6c92', 'imaging', staff_id
FROM sys_staff WHERE staff_code='R001' LIMIT 1
ON DUPLICATE KEY UPDATE role_code=VALUES(role_code), staff_id=VALUES(staff_id), is_active=1;

-- ============================================================
-- 2. 安全追加列
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

CALL sp_add_column_if_missing('ed_lab_order', 'collect_nurse_id', '`collect_nurse_id` BIGINT DEFAULT NULL COMMENT ''采样护士ID'' AFTER `specimen_time`');
CALL sp_add_column_if_missing('ed_lab_order', 'receive_time', '`receive_time` DATETIME DEFAULT NULL COMMENT ''接收时间'' AFTER `collect_nurse_id`');
CALL sp_add_column_if_missing('ed_lab_order', 'lab_technician_id', '`lab_technician_id` BIGINT DEFAULT NULL COMMENT ''检验技师ID'' AFTER `receive_time`');
CALL sp_add_column_if_missing('ed_lab_order', 'confirm_doctor_id', '`confirm_doctor_id` BIGINT DEFAULT NULL COMMENT ''报告确认医生ID'' AFTER `lab_technician_id`');
CALL sp_add_column_if_missing('ed_lab_order', 'confirm_time', '`confirm_time` DATETIME DEFAULT NULL COMMENT ''报告确认时间'' AFTER `confirm_doctor_id`');

CALL sp_add_column_if_missing('ed_imaging_order', 'arrive_time', '`arrive_time` DATETIME DEFAULT NULL COMMENT ''到达检查时间'' AFTER `order_time`');
CALL sp_add_column_if_missing('ed_imaging_order', 'technician_id', '`technician_id` BIGINT DEFAULT NULL COMMENT ''检查技师ID'' AFTER `arrive_time`');
CALL sp_add_column_if_missing('ed_imaging_order', 'confirm_doctor_id', '`confirm_doctor_id` BIGINT DEFAULT NULL COMMENT ''影像确认医生ID'' AFTER `radiologist_id`');
CALL sp_add_column_if_missing('ed_imaging_order', 'confirm_time', '`confirm_time` DATETIME DEFAULT NULL COMMENT ''影像确认时间'' AFTER `confirm_doctor_id`');
CALL sp_add_column_if_missing('ed_imaging_order', 'exam_room', '`exam_room` VARCHAR(30) DEFAULT NULL COMMENT ''检查房间'' AFTER `confirm_time`');

CALL sp_add_column_if_missing('ed_observation', 'responsible_doctor_id', '`responsible_doctor_id` BIGINT DEFAULT NULL COMMENT ''主管医生ID'' AFTER `bed_id`');
CALL sp_add_column_if_missing('ed_observation', 'obs_status', '`obs_status` VARCHAR(20) DEFAULT ''观察中'' COMMENT ''状态(观察中/待入院/已完成)'' AFTER `obs_reason`');
CALL sp_add_column_if_missing('ed_observation', 'latest_reassess_time', '`latest_reassess_time` DATETIME DEFAULT NULL COMMENT ''最近复评时间'' AFTER `reassess_count`');

DROP PROCEDURE IF EXISTS sp_add_column_if_missing;

-- ============================================================
-- 3. 危急值 / 药学 / 会诊 / 留观转归
-- ============================================================

CREATE TABLE IF NOT EXISTS ed_critical_value (
    critical_id         BIGINT          NOT NULL AUTO_INCREMENT,
    lab_id              BIGINT          NOT NULL,
    visit_id            BIGINT          NOT NULL,
    critical_level      VARCHAR(10)     NOT NULL COMMENT 'HH/LL',
    item_name           VARCHAR(100)    NOT NULL,
    result_value        VARCHAR(50)     DEFAULT NULL,
    reference_range     VARCHAR(50)     DEFAULT NULL,
    notify_doctor_id    BIGINT          DEFAULT NULL,
    notify_time         DATETIME        DEFAULT NULL,
    acknowledged_by     BIGINT          DEFAULT NULL,
    acknowledged_at     DATETIME        DEFAULT NULL,
    action_note         VARCHAR(500)    DEFAULT NULL,
    status              VARCHAR(20)     DEFAULT '未确认',
    created_at          DATETIME        DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (critical_id),
    UNIQUE KEY uk_lab_critical (lab_id),
    KEY idx_visit (visit_id),
    KEY idx_status (status)
) ENGINE=InnoDB COMMENT='危急值告警表';

CREATE TABLE IF NOT EXISTS sys_drug_warning_rule (
    rule_id             BIGINT          NOT NULL AUTO_INCREMENT,
    rule_name           VARCHAR(100)    NOT NULL,
    medicine_keyword    VARCHAR(100)    NOT NULL,
    allergy_keyword     VARCHAR(100)    DEFAULT NULL,
    severity            VARCHAR(20)     DEFAULT 'warn',
    warning_message     VARCHAR(300)    NOT NULL,
    is_active           TINYINT(1)      DEFAULT 1,
    created_at          DATETIME        DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (rule_id),
    UNIQUE KEY uk_drug_rule (rule_name)
) ENGINE=InnoDB COMMENT='药学校验规则表';

CREATE TABLE IF NOT EXISTS ed_consultation (
    consult_id          BIGINT          NOT NULL AUTO_INCREMENT,
    visit_id            BIGINT          NOT NULL,
    request_time        DATETIME        NOT NULL,
    request_doctor_id   BIGINT          NOT NULL,
    requested_dept_id   BIGINT          DEFAULT NULL,
    requested_staff_id  BIGINT          DEFAULT NULL,
    consult_reason      VARCHAR(500)    NOT NULL,
    urgency_level       VARCHAR(20)     DEFAULT '普通',
    consult_status      VARCHAR(20)     DEFAULT '待响应',
    response_time       DATETIME        DEFAULT NULL,
    responder_id        BIGINT          DEFAULT NULL,
    consult_opinion     TEXT            DEFAULT NULL,
    advice_plan         TEXT            DEFAULT NULL,
    completed_time      DATETIME        DEFAULT NULL,
    created_at          DATETIME        DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consult_id),
    KEY idx_visit (visit_id),
    KEY idx_status (consult_status)
) ENGINE=InnoDB COMMENT='会诊申请表';

CREATE TABLE IF NOT EXISTS ed_observation_reassess (
    reassess_id         BIGINT          NOT NULL AUTO_INCREMENT,
    obs_id              BIGINT          NOT NULL,
    visit_id            BIGINT          NOT NULL,
    reassess_time       DATETIME        NOT NULL,
    doctor_id           BIGINT          NOT NULL,
    vitals_json         JSON            DEFAULT NULL,
    assessment          TEXT            DEFAULT NULL,
    plan                TEXT            DEFAULT NULL,
    next_reassess_time  DATETIME        DEFAULT NULL,
    created_at          DATETIME        DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (reassess_id),
    KEY idx_obs (obs_id),
    KEY idx_visit (visit_id)
) ENGINE=InnoDB COMMENT='留观复评表';

CREATE TABLE IF NOT EXISTS ed_transfer_request (
    transfer_id         BIGINT          NOT NULL AUTO_INCREMENT,
    visit_id            BIGINT          NOT NULL,
    request_type        VARCHAR(20)     NOT NULL COMMENT '住院/转院',
    request_time        DATETIME        NOT NULL,
    request_doctor_id   BIGINT          NOT NULL,
    target_dept         VARCHAR(50)     DEFAULT NULL,
    target_ward         VARCHAR(50)     DEFAULT NULL,
    bed_request_note    VARCHAR(300)    DEFAULT NULL,
    transfer_status     VARCHAR(20)     DEFAULT '待响应',
    accept_doctor_id    BIGINT          DEFAULT NULL,
    accept_time         DATETIME        DEFAULT NULL,
    reject_reason       VARCHAR(300)    DEFAULT NULL,
    created_at          DATETIME        DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (transfer_id),
    KEY idx_visit (visit_id),
    KEY idx_status (transfer_status)
) ENGINE=InnoDB COMMENT='住院/转院申请表';

INSERT INTO sys_drug_warning_rule (rule_name, medicine_keyword, allergy_keyword, severity, warning_message) VALUES
('青霉素过敏', '青霉素', '青霉素', 'block', '患者存在青霉素过敏史，建议禁用或更换抗菌药物'),
('头孢过敏提示', '头孢', '青霉素', 'warn', '患者青霉素过敏时使用头孢需谨慎，建议再次核对'),
('阿司匹林出血风险', '阿司匹林', '消化道出血', 'warn', '既往有消化道出血病史时需评估阿司匹林用药风险'),
('布洛芬胃溃疡风险', '布洛芬', '胃溃疡', 'warn', '既往胃溃疡病史需谨慎使用NSAIDs')
ON DUPLICATE KEY UPDATE severity=VALUES(severity), warning_message=VALUES(warning_message), is_active=1;

-- ============================================================
-- 4. 闭环工作流视图
-- ============================================================

CREATE OR REPLACE VIEW v_lab_worklist AS
SELECT
    l.lab_id, l.visit_id, l.order_time, l.specimen_type, l.specimen_time, l.collect_nurse_id,
    l.receive_time, l.lab_technician_id, l.lab_status, l.report_time, l.confirm_time,
    l.result_value, l.result_unit, l.result_flag, l.reference_range, l.is_stat,
    e.exam_name, e.exam_category,
    p.patient_name, p.gender, p.age, p.age_unit,
    v.visit_no, v.triage_level, v.triage_color, v.attending_doctor_id
FROM ed_lab_order l
JOIN ed_visit v ON l.visit_id = v.visit_id
JOIN patient_info p ON v.patient_id = p.patient_id
LEFT JOIN sys_exam_dict e ON l.exam_id = e.exam_id
WHERE v.visit_status NOT IN ('已离院','已转院','死亡');

CREATE OR REPLACE VIEW v_critical_values_active AS
SELECT
    c.critical_id, c.lab_id, c.visit_id, c.critical_level, c.item_name, c.result_value,
    c.reference_range, c.notify_doctor_id, c.notify_time, c.acknowledged_by, c.acknowledged_at,
    c.action_note, c.status, c.created_at,
    p.patient_name, v.visit_no, v.triage_level, v.bed_id, b.bed_code
FROM ed_critical_value c
JOIN ed_visit v ON c.visit_id = v.visit_id
JOIN patient_info p ON v.patient_id = p.patient_id
LEFT JOIN ed_bed b ON v.bed_id = b.bed_id
WHERE c.status <> '已处理'
ORDER BY c.created_at DESC;

CREATE OR REPLACE VIEW v_imaging_worklist AS
SELECT
    i.imaging_id, i.visit_id, i.order_time, i.arrive_time, i.exam_time, i.report_time,
    i.imaging_status, i.is_stat, i.technician_id, i.radiologist_id, i.confirm_time,
    i.exam_room, i.impression,
    e.exam_name, e.exam_category,
    p.patient_name, p.gender, p.age, p.age_unit,
    v.visit_no, v.triage_level, v.triage_color
FROM ed_imaging_order i
JOIN ed_visit v ON i.visit_id = v.visit_id
JOIN patient_info p ON v.patient_id = p.patient_id
LEFT JOIN sys_exam_dict e ON i.exam_id = e.exam_id
WHERE v.visit_status NOT IN ('已离院','已转院','死亡');

CREATE OR REPLACE VIEW v_consultation_pending AS
SELECT
    c.consult_id, c.visit_id, c.request_time, c.request_doctor_id, c.requested_dept_id, c.requested_staff_id,
    c.consult_reason, c.urgency_level, c.consult_status, c.response_time, c.responder_id,
    p.patient_name, v.visit_no, v.triage_level, d.dept_name AS requested_dept_name,
    s.staff_name AS requested_staff_name, sd.staff_name AS request_doctor_name
FROM ed_consultation c
JOIN ed_visit v ON c.visit_id = v.visit_id
JOIN patient_info p ON v.patient_id = p.patient_id
LEFT JOIN sys_department d ON c.requested_dept_id = d.dept_id
LEFT JOIN sys_staff s ON c.requested_staff_id = s.staff_id
LEFT JOIN sys_staff sd ON c.request_doctor_id = sd.staff_id
WHERE c.consult_status IN ('待响应','进行中')
ORDER BY CASE c.urgency_level WHEN '紧急' THEN 1 WHEN '加急' THEN 2 ELSE 3 END, c.request_time ASC;

CREATE OR REPLACE VIEW v_observation_active AS
SELECT
    o.obs_id, o.visit_id, o.bed_id, o.responsible_doctor_id, o.obs_start, o.obs_end,
    o.obs_duration, o.obs_reason, o.obs_status, o.reassess_count, o.latest_reassess_time,
    o.outcome, o.dest_dept, o.dest_ward,
    p.patient_name, p.gender, p.age, p.age_unit,
    v.visit_no, v.triage_level, v.triage_color, b.bed_code, s.staff_name AS responsible_doctor_name
FROM ed_observation o
JOIN ed_visit v ON o.visit_id = v.visit_id
JOIN patient_info p ON v.patient_id = p.patient_id
LEFT JOIN ed_bed b ON o.bed_id = b.bed_id
LEFT JOIN sys_staff s ON o.responsible_doctor_id = s.staff_id
WHERE o.obs_status IN ('观察中','待入院')
ORDER BY o.obs_start ASC;

-- ============================================================
-- 5. 为历史已报告危急值补充告警
-- ============================================================

INSERT IGNORE INTO ed_critical_value (lab_id, visit_id, critical_level, item_name, result_value, reference_range, notify_doctor_id, notify_time, status)
SELECT
    l.lab_id, l.visit_id, l.result_flag, e.exam_name, CAST(l.result_value AS CHAR), l.reference_range,
    v.attending_doctor_id, l.report_time,
    CASE WHEN l.confirm_time IS NOT NULL THEN '已处理' ELSE '未确认' END
FROM ed_lab_order l
JOIN ed_visit v ON l.visit_id = v.visit_id
LEFT JOIN sys_exam_dict e ON l.exam_id = e.exam_id
WHERE l.result_flag IN ('HH','LL');
