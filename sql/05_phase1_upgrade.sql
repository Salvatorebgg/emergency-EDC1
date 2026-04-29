-- ============================================================
-- 急诊科 EDC 系统 - 第一阶段成熟化升级
-- 功能: 登录权限、患者检索、智能分诊、医生站、护士站、医嘱闭环
-- 执行前提: 已依次执行 01_create_database.sql ~ 04_views_procedures.sql
-- ============================================================

USE ed_emergency;

-- ============================================================
-- 1. 安全与角色
-- ============================================================

CREATE TABLE IF NOT EXISTS sys_role (
    role_code       VARCHAR(30)     NOT NULL COMMENT '角色编码',
    role_name       VARCHAR(50)     NOT NULL COMMENT '角色名称',
    role_desc       VARCHAR(200)    DEFAULT NULL,
    is_active       TINYINT(1)      DEFAULT 1,
    created_at      DATETIME        DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (role_code)
) ENGINE=InnoDB COMMENT='系统角色表';

CREATE TABLE IF NOT EXISTS sys_user (
    user_id         BIGINT          NOT NULL AUTO_INCREMENT COMMENT '用户ID',
    username        VARCHAR(50)     NOT NULL COMMENT '登录名',
    password_hash   VARCHAR(128)    NOT NULL COMMENT 'SHA256密码摘要',
    role_code       VARCHAR(30)     NOT NULL COMMENT '角色编码',
    staff_id        BIGINT          DEFAULT NULL COMMENT '关联员工ID',
    is_active       TINYINT(1)      DEFAULT 1,
    last_login_at   DATETIME        DEFAULT NULL,
    created_at      DATETIME        DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME        DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id),
    UNIQUE KEY uk_username (username),
    KEY idx_role (role_code),
    KEY idx_staff (staff_id)
) ENGINE=InnoDB COMMENT='系统用户表';

INSERT INTO sys_role (role_code, role_name, role_desc) VALUES
('admin', '管理员', '系统配置、审计和字典维护'),
('triage', '分诊护士', '患者登记、智能分诊和候诊队列管理'),
('doctor', '急诊医生', '医生工作站、病历、诊断和医嘱'),
('nurse', '急诊护士', '护士工作站、医嘱执行和护理记录'),
('lab', '检验人员', '检验采样、报告与危急值'),
('imaging', '影像人员', '影像检查与报告')
ON DUPLICATE KEY UPDATE role_name=VALUES(role_name), role_desc=VALUES(role_desc), is_active=1;

-- 默认密码均为 123456；生产环境必须改为强密码和更安全的哈希算法。
INSERT INTO sys_user (username, password_hash, role_code, staff_id)
SELECT 'admin', '8d969eef6ecad3c29a3a629280e686cf0c3f5d5a86aff3ca12020c923adc6c92', 'admin', staff_id
FROM sys_staff WHERE staff_code='A001' LIMIT 1
ON DUPLICATE KEY UPDATE role_code=VALUES(role_code), staff_id=VALUES(staff_id), is_active=1;

INSERT INTO sys_user (username, password_hash, role_code, staff_id)
SELECT 'doctor', '8d969eef6ecad3c29a3a629280e686cf0c3f5d5a86aff3ca12020c923adc6c92', 'doctor', staff_id
FROM sys_staff WHERE staff_code='D001' LIMIT 1
ON DUPLICATE KEY UPDATE role_code=VALUES(role_code), staff_id=VALUES(staff_id), is_active=1;

INSERT INTO sys_user (username, password_hash, role_code, staff_id)
SELECT 'nurse', '8d969eef6ecad3c29a3a629280e686cf0c3f5d5a86aff3ca12020c923adc6c92', 'nurse', staff_id
FROM sys_staff WHERE staff_code='N001' LIMIT 1
ON DUPLICATE KEY UPDATE role_code=VALUES(role_code), staff_id=VALUES(staff_id), is_active=1;

INSERT INTO sys_user (username, password_hash, role_code, staff_id)
SELECT 'triage', '8d969eef6ecad3c29a3a629280e686cf0c3f5d5a86aff3ca12020c923adc6c92', 'triage', staff_id
FROM sys_staff WHERE staff_code='T001' LIMIT 1
ON DUPLICATE KEY UPDATE role_code=VALUES(role_code), staff_id=VALUES(staff_id), is_active=1;

-- ============================================================
-- 2. 安全追加列工具
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

CALL sp_add_column_if_missing('ed_visit', 'priority_score', '`priority_score` INT DEFAULT NULL COMMENT ''分诊优先分'' AFTER `triage_color`');
CALL sp_add_column_if_missing('ed_visit', 'triage_reason', '`triage_reason` VARCHAR(500) DEFAULT NULL COMMENT ''智能分诊依据'' AFTER `priority_score`');

CALL sp_add_column_if_missing('ed_order', 'review_status', '`review_status` VARCHAR(20) DEFAULT ''未审核'' COMMENT ''审核状态(未审核/已审核/已驳回)'' AFTER `order_status`');
CALL sp_add_column_if_missing('ed_order', 'reviewer_id', '`reviewer_id` BIGINT DEFAULT NULL COMMENT ''审核人ID'' AFTER `review_status`');
CALL sp_add_column_if_missing('ed_order', 'review_time', '`review_time` DATETIME DEFAULT NULL COMMENT ''审核时间'' AFTER `reviewer_id`');
CALL sp_add_column_if_missing('ed_order', 'stop_time', '`stop_time` DATETIME DEFAULT NULL COMMENT ''停止/取消时间'' AFTER `execute_nurse_id`');
CALL sp_add_column_if_missing('ed_order', 'stop_reason', '`stop_reason` VARCHAR(200) DEFAULT NULL COMMENT ''停止原因'' AFTER `stop_time`');

DROP PROCEDURE IF EXISTS sp_add_column_if_missing;

-- ============================================================
-- 3. 智能分诊规则与告警
-- ============================================================

CREATE TABLE IF NOT EXISTS ed_triage_rule (
    rule_id         BIGINT          NOT NULL AUTO_INCREMENT,
    rule_name       VARCHAR(100)    NOT NULL,
    rule_type       VARCHAR(30)     NOT NULL COMMENT 'keyword/vital/age/arrival',
    match_pattern   VARCHAR(200)    NOT NULL,
    score           INT             NOT NULL DEFAULT 0,
    target_level    TINYINT         DEFAULT NULL,
    is_active       TINYINT(1)      DEFAULT 1,
    created_at      DATETIME        DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (rule_id),
    UNIQUE KEY uk_rule_name (rule_name),
    KEY idx_rule_type (rule_type),
    KEY idx_active (is_active)
) ENGINE=InnoDB COMMENT='智能分诊规则表';

CREATE TABLE IF NOT EXISTS ed_alert_event (
    alert_id        BIGINT          NOT NULL AUTO_INCREMENT,
    visit_id        BIGINT          DEFAULT NULL,
    alert_type      VARCHAR(30)     NOT NULL COMMENT 'triage/order/lab/system',
    severity        VARCHAR(20)     NOT NULL COMMENT 'info/warn/critical',
    title           VARCHAR(100)    NOT NULL,
    message         VARCHAR(500)    DEFAULT NULL,
    alert_status    VARCHAR(20)     DEFAULT '未处理',
    created_by      BIGINT          DEFAULT NULL,
    handled_by      BIGINT          DEFAULT NULL,
    handled_at      DATETIME        DEFAULT NULL,
    created_at      DATETIME        DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (alert_id),
    KEY idx_visit (visit_id),
    KEY idx_status (alert_status),
    KEY idx_severity (severity)
) ENGINE=InnoDB COMMENT='系统告警事件表';

INSERT INTO ed_triage_rule (rule_name, rule_type, match_pattern, score, target_level) VALUES
('濒危关键词', 'keyword', '心脏骤停|呼吸心跳停止|意识丧失|昏迷|大出血|休克', 100, 1),
('危重关键词', 'keyword', '胸痛|呼吸困难|气促|偏瘫|中风|卒中|剧烈腹痛|中毒|车祸|坠落', 75, 2),
('急症关键词', 'keyword', '发热|腹痛|呕吐|头晕|腹泻|腰痛|皮疹', 45, 3),
('低血氧', 'vital', 'SpO2<90', 80, 1),
('危险血压', 'vital', 'SBP<90 OR SBP>=180', 45, 2),
('120转入', 'arrival', '120急救', 15, NULL)
ON DUPLICATE KEY UPDATE is_active=VALUES(is_active);

-- ============================================================
-- 4. 医生站：诊断结构化
-- ============================================================

CREATE TABLE IF NOT EXISTS ed_diagnosis (
    diagnosis_id    BIGINT          NOT NULL AUTO_INCREMENT,
    visit_id        BIGINT          NOT NULL,
    icd_code        VARCHAR(20)     DEFAULT NULL,
    diagnosis_name  VARCHAR(100)    NOT NULL,
    diagnosis_type  VARCHAR(30)     DEFAULT '初步诊断',
    doctor_id       BIGINT          NOT NULL,
    diagnose_time   DATETIME        NOT NULL,
    is_primary      TINYINT(1)      DEFAULT 1,
    created_at      DATETIME        DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (diagnosis_id),
    KEY idx_visit (visit_id),
    KEY idx_icd (icd_code),
    KEY idx_doctor (doctor_id)
) ENGINE=InnoDB COMMENT='结构化诊断表';

-- ============================================================
-- 5. 护士站：医嘱执行闭环
-- ============================================================

CREATE TABLE IF NOT EXISTS ed_order_execution (
    execution_id    BIGINT          NOT NULL AUTO_INCREMENT,
    order_id        BIGINT          NOT NULL,
    execute_time    DATETIME        NOT NULL,
    execute_nurse_id BIGINT         NOT NULL,
    execution_status VARCHAR(20)    DEFAULT '已执行',
    result_note     VARCHAR(500)    DEFAULT NULL,
    vital_snapshot  JSON            DEFAULT NULL,
    created_at      DATETIME        DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (execution_id),
    KEY idx_order (order_id),
    KEY idx_nurse (execute_nurse_id),
    KEY idx_time (execute_time)
) ENGINE=InnoDB COMMENT='医嘱执行明细表';

-- ============================================================
-- 6. 工作站视图
-- ============================================================

CREATE OR REPLACE VIEW v_doctor_worklist AS
SELECT 
    v.visit_id, v.visit_no, p.patient_name, p.gender, p.age, p.age_unit,
    v.visit_time, v.visit_status, v.triage_level, v.triage_color, v.priority_score,
    v.chief_complaint, v.attending_doctor_id, s.staff_name AS attending_doctor_name,
    b.bed_code, b.bed_zone,
    TIMESTAMPDIFF(MINUTE, v.visit_time, IFNULL(v.outcome_time, NOW())) AS stay_minutes,
    (SELECT COUNT(*) FROM ed_order o WHERE o.visit_id=v.visit_id AND o.order_status='待执行') AS pending_orders,
    (SELECT COUNT(*) FROM ed_lab_order l WHERE l.visit_id=v.visit_id AND l.lab_status <> '已报告') AS pending_labs,
    (SELECT MAX(record_time) FROM ed_medical_record mr WHERE mr.visit_id=v.visit_id) AS last_record_time
FROM ed_visit v
JOIN patient_info p ON v.patient_id = p.patient_id
LEFT JOIN sys_staff s ON v.attending_doctor_id = s.staff_id
LEFT JOIN ed_bed b ON v.bed_id = b.bed_id
WHERE v.visit_status NOT IN ('已离院','已转院','死亡');

CREATE OR REPLACE VIEW v_nurse_order_tasks AS
SELECT
    o.order_id, o.visit_id, o.order_time, o.order_type, o.order_content, o.dosage,
    o.frequency, o.route, o.is_stat, o.order_status, o.review_status,
    v.visit_no, p.patient_name, p.gender, p.age, p.age_unit, v.triage_level, v.triage_color,
    b.bed_code, s.staff_name AS doctor_name
FROM ed_order o
JOIN ed_visit v ON o.visit_id = v.visit_id
JOIN patient_info p ON v.patient_id = p.patient_id
LEFT JOIN ed_bed b ON v.bed_id = b.bed_id
LEFT JOIN sys_staff s ON o.doctor_id = s.staff_id
WHERE v.visit_status NOT IN ('已离院','已转院','死亡');

-- 老数据默认视为已审核，避免护士站出现大量“未审核但待执行”的历史医嘱。
UPDATE ed_order SET review_status='已审核' WHERE review_status='未审核';
