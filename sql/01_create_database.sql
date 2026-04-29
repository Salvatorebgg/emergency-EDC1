-- ============================================================
-- 急诊科 EDC 系统 - 数据库创建脚本
-- 版本: 1.0
-- 描述: 模拟医院急诊科电子数据采集系统
-- ============================================================

CREATE DATABASE IF NOT EXISTS ed_emergency 
    DEFAULT CHARACTER SET utf8mb4 
    DEFAULT COLLATE utf8mb4_unicode_ci;

USE ed_emergency;

-- ============================================================
-- 1. 基础字典表
-- ============================================================

-- 科室信息
DROP TABLE IF EXISTS sys_department;
CREATE TABLE sys_department (
    dept_id         BIGINT          NOT NULL AUTO_INCREMENT  COMMENT '科室ID',
    dept_code       VARCHAR(20)     NOT NULL                 COMMENT '科室编码',
    dept_name       VARCHAR(50)     NOT NULL                 COMMENT '科室名称',
    dept_category   VARCHAR(20)     DEFAULT NULL             COMMENT '科室类别(内科/外科/急诊/ICU等)',
    parent_id       BIGINT          DEFAULT 0                COMMENT '上级科室ID',
    is_active       TINYINT(1)      DEFAULT 1                COMMENT '是否启用',
    sort_order      INT             DEFAULT 0                COMMENT '排序号',
    created_at      DATETIME        DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME        DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (dept_id),
    UNIQUE KEY uk_dept_code (dept_code)
) ENGINE=InnoDB COMMENT='科室信息表';

-- 员工/医护信息
DROP TABLE IF EXISTS sys_staff;
CREATE TABLE sys_staff (
    staff_id        BIGINT          NOT NULL AUTO_INCREMENT  COMMENT '员工ID',
    staff_code      VARCHAR(20)     NOT NULL                 COMMENT '工号',
    staff_name      VARCHAR(50)     NOT NULL                 COMMENT '姓名',
    gender          CHAR(1)         DEFAULT NULL             COMMENT '性别(M/F)',
    title           VARCHAR(30)     DEFAULT NULL             COMMENT '职称(主任医师/副主任医师/主治医师/住院医师/护士等)',
    dept_id         BIGINT          DEFAULT NULL             COMMENT '所属科室ID',
    role_type       VARCHAR(20)     NOT NULL                 COMMENT '角色类型(医生/护士/分诊员/管理员)',
    is_active       TINYINT(1)      DEFAULT 1                COMMENT '是否在职',
    phone           VARCHAR(20)     DEFAULT NULL             COMMENT '联系电话',
    created_at      DATETIME        DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME        DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (staff_id),
    UNIQUE KEY uk_staff_code (staff_code),
    KEY idx_dept (dept_id)
) ENGINE=InnoDB COMMENT='员工信息表';

-- 诊断字典(ICD-10子集)
DROP TABLE IF EXISTS sys_diagnosis_dict;
CREATE TABLE sys_diagnosis_dict (
    dict_id         BIGINT          NOT NULL AUTO_INCREMENT  COMMENT '字典ID',
    icd_code        VARCHAR(10)     NOT NULL                 COMMENT 'ICD-10编码',
    icd_name        VARCHAR(200)    NOT NULL                 COMMENT 'ICD-10名称',
    icd_category    VARCHAR(50)     DEFAULT NULL             COMMENT '疾病分类',
    is_common       TINYINT(1)      DEFAULT 0                COMMENT '是否常见急诊诊断',
    sort_order      INT             DEFAULT 0,
    PRIMARY KEY (dict_id),
    UNIQUE KEY uk_icd_code (icd_code),
    KEY idx_category (icd_category)
) ENGINE=InnoDB COMMENT='诊断字典表';

-- 药品字典
DROP TABLE IF EXISTS sys_medicine_dict;
CREATE TABLE sys_medicine_dict (
    medicine_id     BIGINT          NOT NULL AUTO_INCREMENT  COMMENT '药品ID',
    medicine_code   VARCHAR(20)     NOT NULL                 COMMENT '药品编码',
    medicine_name   VARCHAR(100)    NOT NULL                 COMMENT '药品通用名',
    specification   VARCHAR(100)    DEFAULT NULL             COMMENT '规格',
    dosage_form     VARCHAR(30)     DEFAULT NULL             COMMENT '剂型(片剂/注射剂/胶囊等)',
    category        VARCHAR(30)     DEFAULT NULL             COMMENT '药品分类(抗生素/止痛/急救等)',
    is_emergency    TINYINT(1)      DEFAULT 0                COMMENT '是否急救药品',
    unit            VARCHAR(20)     DEFAULT NULL             COMMENT '计量单位',
    created_at      DATETIME        DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (medicine_id),
    UNIQUE KEY uk_medicine_code (medicine_code)
) ENGINE=InnoDB COMMENT='药品字典表';

-- 检查检验项目字典
DROP TABLE IF EXISTS sys_exam_dict;
CREATE TABLE sys_exam_dict (
    exam_id         BIGINT          NOT NULL AUTO_INCREMENT  COMMENT '检查项目ID',
    exam_code       VARCHAR(20)     NOT NULL                 COMMENT '项目编码',
    exam_name       VARCHAR(100)    NOT NULL                 COMMENT '项目名称',
    exam_category   VARCHAR(20)     NOT NULL                 COMMENT '类别(检验/影像/心电图/超声)',
    exam_subcat     VARCHAR(50)     DEFAULT NULL             COMMENT '子类别',
    specimen_type   VARCHAR(30)     DEFAULT NULL             COMMENT '标本类型(血液/尿液/等)',
    reference_low   DECIMAL(10,2)   DEFAULT NULL             COMMENT '参考值下限',
    reference_high  DECIMAL(10,2)   DEFAULT NULL             COMMENT '参考值上限',
    reference_unit  VARCHAR(20)     DEFAULT NULL             COMMENT '参考值单位',
    turnaround_min  INT             DEFAULT NULL             COMMENT '报告周转时间(分钟)',
    is_stat         TINYINT(1)      DEFAULT 0                COMMENT '是否急诊加急项目',
    created_at      DATETIME        DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (exam_id),
    UNIQUE KEY uk_exam_code (exam_code),
    KEY idx_category (exam_category)
) ENGINE=InnoDB COMMENT='检查检验项目字典表';

-- 床位信息
DROP TABLE IF EXISTS ed_bed;
CREATE TABLE ed_bed (
    bed_id          BIGINT          NOT NULL AUTO_INCREMENT  COMMENT '床位ID',
    bed_code        VARCHAR(10)     NOT NULL                 COMMENT '床位编号',
    bed_zone        VARCHAR(20)     NOT NULL                 COMMENT '区域(红区-抢救/黄区-重症/绿区-普通)',
    bed_type        VARCHAR(20)     DEFAULT NULL             COMMENT '床位类型(抢救床/观察床/输液椅/平车)',
    bed_status      VARCHAR(20)     DEFAULT '空闲'            COMMENT '状态(空闲/占用/清洁中/维修)',
    current_visit_id BIGINT         DEFAULT NULL             COMMENT '当前占用患者就诊ID',
    has_monitor     TINYINT(1)      DEFAULT 0                COMMENT '是否有监护仪',
    has_ventilator  TINYINT(1)      DEFAULT 0                COMMENT '是否有呼吸机',
    sort_order      INT             DEFAULT 0,
    created_at      DATETIME        DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME        DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (bed_id),
    UNIQUE KEY uk_bed_code (bed_code),
    KEY idx_zone (bed_zone),
    KEY idx_status (bed_status)
) ENGINE=InnoDB COMMENT='急诊床位表';

-- ============================================================
-- 2. 患者管理核心表
-- ============================================================

-- 患者基本信息
DROP TABLE IF EXISTS patient_info;
CREATE TABLE patient_info (
    patient_id      BIGINT          NOT NULL AUTO_INCREMENT  COMMENT '患者ID',
    patient_no      VARCHAR(20)     NOT NULL                 COMMENT '患者编号(院内唯一)',
    id_card_no      VARCHAR(18)     DEFAULT NULL             COMMENT '身份证号',
    patient_name    VARCHAR(50)     NOT NULL                 COMMENT '姓名',
    gender          CHAR(1)         NOT NULL                 COMMENT '性别(M/F/U)',
    birth_date      DATE            DEFAULT NULL             COMMENT '出生日期',
    age             INT             DEFAULT NULL             COMMENT '年龄',
    age_unit        VARCHAR(5)      DEFAULT '岁'             COMMENT '年龄单位(岁/月/天/小时)',
    phone           VARCHAR(20)     DEFAULT NULL             COMMENT '联系电话',
    address         VARCHAR(200)    DEFAULT NULL             COMMENT '住址',
    emergency_contact VARCHAR(50)   DEFAULT NULL             COMMENT '紧急联系人',
    emergency_phone VARCHAR(20)     DEFAULT NULL             COMMENT '紧急联系电话',
    blood_type      VARCHAR(5)      DEFAULT NULL             COMMENT '血型(A/B/O/AB/Rh)',
    allergy_history TEXT            DEFAULT NULL             COMMENT '过敏史',
    past_history    TEXT            DEFAULT NULL             COMMENT '既往史',
    insurance_type  VARCHAR(20)     DEFAULT NULL             COMMENT '医保类型(城镇职工/城乡居民/自费/其他)',
    created_at      DATETIME        DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME        DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (patient_id),
    UNIQUE KEY uk_patient_no (patient_no),
    KEY idx_id_card (id_card_no),
    KEY idx_name (patient_name),
    KEY idx_phone (phone)
) ENGINE=InnoDB COMMENT='患者基本信息表';

-- ============================================================
-- 3. 急诊就诊流程表
-- ============================================================

-- 急诊就诊主记录
DROP TABLE IF EXISTS ed_visit;
CREATE TABLE ed_visit (
    visit_id        BIGINT          NOT NULL AUTO_INCREMENT  COMMENT '就诊ID',
    visit_no        VARCHAR(20)     NOT NULL                 COMMENT '就诊流水号',
    patient_id      BIGINT          NOT NULL                 COMMENT '患者ID',
    visit_date      DATE            NOT NULL                 COMMENT '就诊日期',
    visit_time      DATETIME        NOT NULL                 COMMENT '就诊时间',
    arrival_mode    VARCHAR(20)     DEFAULT NULL             COMMENT '来诊方式(步行/轮椅/平车/120急救/其他)',
    chief_complaint VARCHAR(500)    NOT NULL                 COMMENT '主诉',
    present_illness TEXT            DEFAULT NULL             COMMENT '现病史',
    triage_level    TINYINT         DEFAULT NULL             COMMENT '分诊级别(1-5级, 1最紧急)',
    triage_color    VARCHAR(10)     DEFAULT NULL             COMMENT '分诊颜色(红/橙/黄/绿/蓝)',
    triage_time     DATETIME        DEFAULT NULL             COMMENT '分诊时间',
    triage_nurse_id BIGINT          DEFAULT NULL             COMMENT '分诊护士ID',
    triage_vitals   JSON            DEFAULT NULL             COMMENT '分诊生命体征{HR,BP,Temp,RR,SpO2,Pain}',
    attending_doctor_id BIGINT      DEFAULT NULL             COMMENT '主治医生ID',
    bed_id          BIGINT          DEFAULT NULL             COMMENT '分配床位ID',
    visit_status    VARCHAR(20)     NOT NULL DEFAULT '分诊中' COMMENT '状态(分诊中/候诊/就诊中/观察中/处置中/待入院/已离院/已转院/死亡)',
    outcome         VARCHAR(20)     DEFAULT NULL             COMMENT '去向(离院回家/住院/转院/留观/死亡)',
    outcome_time    DATETIME        DEFAULT NULL             COMMENT '离科时间',
    icd_code        VARCHAR(10)     DEFAULT NULL             COMMENT '主要诊断ICD编码',
    icd_code2       VARCHAR(10)     DEFAULT NULL             COMMENT '次要诊断ICD编码',
    is_green_channel TINYINT(1)     DEFAULT 0                COMMENT '是否绿色通道',
    is_trauma       TINYINT(1)      DEFAULT 0                COMMENT '是否创伤',
    is_pediatric    TINYINT(1)      DEFAULT 0                COMMENT '是否儿科',
    is_120_transfer TINYINT(1)      DEFAULT 0                COMMENT '是否120转入',
    prehospital_info JSON          DEFAULT NULL              COMMENT '院前急救信息',
    created_at      DATETIME        DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME        DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (visit_id),
    UNIQUE KEY uk_visit_no (visit_no),
    KEY idx_patient (patient_id),
    KEY idx_visit_date (visit_date),
    KEY idx_status (visit_status),
    KEY idx_triage (triage_level),
    KEY idx_doctor (attending_doctor_id)
) ENGINE=InnoDB COMMENT='急诊就诊主记录表';

-- 分诊评估详情
DROP TABLE IF EXISTS ed_triage_assessment;
CREATE TABLE ed_triage_assessment (
    assessment_id   BIGINT          NOT NULL AUTO_INCREMENT  COMMENT '评估ID',
    visit_id        BIGINT          NOT NULL                 COMMENT '就诊ID',
    assess_time     DATETIME        NOT NULL                 COMMENT '评估时间',
    nurse_id        BIGINT          NOT NULL                 COMMENT '评估护士ID',
    consciousness   VARCHAR(20)     DEFAULT NULL             COMMENT '意识状态(清醒/嗜睡/昏睡/昏迷)',
    pain_score      TINYINT         DEFAULT NULL             COMMENT '疼痛评分(0-10)',
    hr              INT             DEFAULT NULL             COMMENT '心率(次/分)',
    bp_systolic     INT             DEFAULT NULL             COMMENT '收缩压(mmHg)',
    bp_diastolic    INT             DEFAULT NULL             COMMENT '舒张压(mmHg)',
    temperature     DECIMAL(4,1)    DEFAULT NULL             COMMENT '体温(℃)',
    rr              INT             DEFAULT NULL             COMMENT '呼吸频率(次/分)',
    spo2            INT             DEFAULT NULL             COMMENT '血氧饱和度(%)',
    weight          DECIMAL(5,1)    DEFAULT NULL             COMMENT '体重(kg)',
    fall_risk       VARCHAR(10)     DEFAULT NULL             COMMENT '跌倒风险(低/中/高)',
    skin_integrity  VARCHAR(10)     DEFAULT NULL             COMMENT '皮肤完整性(完整/破损)',
    triage_level    TINYINT         NOT NULL                 COMMENT '分诊级别',
    triage_category VARCHAR(50)     DEFAULT NULL             COMMENT '分诊类别(创伤/胸痛/卒中/腹痛/发热等)',
    chief_complaint VARCHAR(500)    DEFAULT NULL             COMMENT '主诉',
    brief_history   TEXT            DEFAULT NULL             COMMENT '简要病史',
    allergy_flag    TINYINT(1)      DEFAULT 0                COMMENT '过敏标记',
    pregnancy_flag  TINYINT(1)      DEFAULT 0                COMMENT '妊娠标记',
    created_at      DATETIME        DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (assessment_id),
    KEY idx_visit (visit_id),
    KEY idx_level (triage_level)
) ENGINE=InnoDB COMMENT='分诊评估详情表';

-- 医生诊疗记录
DROP TABLE IF EXISTS ed_medical_record;
CREATE TABLE ed_medical_record (
    record_id       BIGINT          NOT NULL AUTO_INCREMENT  COMMENT '记录ID',
    visit_id        BIGINT          NOT NULL                 COMMENT '就诊ID',
    doctor_id       BIGINT          NOT NULL                 COMMENT '医生ID',
    record_time     DATETIME        NOT NULL                 COMMENT '记录时间',
    record_type     VARCHAR(20)     NOT NULL DEFAULT '初诊'  COMMENT '记录类型(初诊/复评/交班/抢救)',
    chief_complaint VARCHAR(500)    DEFAULT NULL             COMMENT '主诉',
    present_illness TEXT            DEFAULT NULL             COMMENT '现病史',
    physical_exam   TEXT            DEFAULT NULL             COMMENT '体格检查',
    assessment      TEXT            DEFAULT NULL             COMMENT '初步诊断/评估',
    treatment_plan  TEXT            DEFAULT NULL             COMMENT '治疗方案',
    doctor_orders   TEXT            DEFAULT NULL             COMMENT '医嘱摘要',
    hr              INT             DEFAULT NULL             COMMENT '心率',
    bp_systolic     INT             DEFAULT NULL             COMMENT '收缩压',
    bp_diastolic    INT             DEFAULT NULL             COMMENT '舒张压',
    temperature     DECIMAL(4,1)    DEFAULT NULL             COMMENT '体温',
    rr              INT             DEFAULT NULL             COMMENT '呼吸频率',
    spo2            INT             DEFAULT NULL             COMMENT '血氧',
    created_at      DATETIME        DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (record_id),
    KEY idx_visit (visit_id),
    KEY idx_doctor (doctor_id),
    KEY idx_time (record_time)
) ENGINE=InnoDB COMMENT='医生诊疗记录表';

-- ============================================================
-- 4. 医嘱与处方
-- ============================================================

-- 医嘱表
DROP TABLE IF EXISTS ed_order;
CREATE TABLE ed_order (
    order_id        BIGINT          NOT NULL AUTO_INCREMENT  COMMENT '医嘱ID',
    visit_id        BIGINT          NOT NULL                 COMMENT '就诊ID',
    order_time      DATETIME        NOT NULL                 COMMENT '开立时间',
    doctor_id       BIGINT          NOT NULL                 COMMENT '开立医生ID',
    order_type      VARCHAR(20)     NOT NULL                 COMMENT '医嘱类型(药品/检验/检查/处置/护理/饮食)',
    order_category  VARCHAR(20)     DEFAULT NULL             COMMENT '医嘱类别(长期/临时)',
    order_content   VARCHAR(500)    NOT NULL                 COMMENT '医嘱内容',
    item_code       VARCHAR(20)     DEFAULT NULL             COMMENT '关联项目编码(药品/检查)',
    dosage          VARCHAR(50)     DEFAULT NULL             COMMENT '剂量',
    frequency       VARCHAR(30)     DEFAULT NULL             COMMENT '频次(QD/BID/TID/QID/PRN/STAT等)',
    route           VARCHAR(20)     DEFAULT NULL             COMMENT '给药途径(口服/静脉注射/肌肉注射/外用等)',
    duration_days   INT             DEFAULT NULL             COMMENT '疗程天数',
    is_stat         TINYINT(1)      DEFAULT 0                COMMENT '是否加急',
    order_status    VARCHAR(20)     DEFAULT '待执行'          COMMENT '状态(待执行/执行中/已完成/已取消)',
    execute_time    DATETIME        DEFAULT NULL             COMMENT '执行时间',
    execute_nurse_id BIGINT         DEFAULT NULL             COMMENT '执行护士ID',
    cancel_reason   VARCHAR(200)    DEFAULT NULL             COMMENT '取消原因',
    created_at      DATETIME        DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME        DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (order_id),
    KEY idx_visit (visit_id),
    KEY idx_doctor (doctor_id),
    KEY idx_type (order_type),
    KEY idx_status (order_status)
) ENGINE=InnoDB COMMENT='医嘱表';

-- ============================================================
-- 5. 检查检验
-- ============================================================

-- 检验申请与结果
DROP TABLE IF EXISTS ed_lab_order;
CREATE TABLE ed_lab_order (
    lab_id          BIGINT          NOT NULL AUTO_INCREMENT  COMMENT '检验ID',
    visit_id        BIGINT          NOT NULL                 COMMENT '就诊ID',
    order_id        BIGINT          DEFAULT NULL             COMMENT '关联回医嘱ID',
    exam_id         BIGINT          NOT NULL                 COMMENT '检查项目ID',
    order_time      DATETIME        NOT NULL                 COMMENT '申请时间',
    doctor_id       BIGINT          NOT NULL                 COMMENT '申请医生ID',
    specimen_type   VARCHAR(30)     DEFAULT NULL             COMMENT '标本类型',
    specimen_time   DATETIME        DEFAULT NULL             COMMENT '采标本时间',
    is_stat         TINYINT(1)      DEFAULT 0                COMMENT '是否加急',
    lab_status      VARCHAR(20)     DEFAULT '待采集'          COMMENT '状态(待采集/已采集/检验中/已报告)',
    report_time     DATETIME        DEFAULT NULL             COMMENT '报告时间',
    result_value    DECIMAL(12,4)   DEFAULT NULL             COMMENT '结果数值',
    result_unit     VARCHAR(20)     DEFAULT NULL             COMMENT '结果单位',
    result_flag     VARCHAR(5)      DEFAULT NULL             COMMENT '异常标志(N/H/L/HH/LL)',
    result_text     VARCHAR(200)    DEFAULT NULL             COMMENT '文字结果(用于定性项目)',
    reference_range VARCHAR(50)     DEFAULT NULL             COMMENT '参考范围',
    created_at      DATETIME        DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME        DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (lab_id),
    KEY idx_visit (visit_id),
    KEY idx_exam (exam_id),
    KEY idx_status (lab_status)
) ENGINE=InnoDB COMMENT='检验申请与结果表';

-- 影像/检查申请与结果
DROP TABLE IF EXISTS ed_imaging_order;
CREATE TABLE ed_imaging_order (
    imaging_id      BIGINT          NOT NULL AUTO_INCREMENT  COMMENT '影像ID',
    visit_id        BIGINT          NOT NULL                 COMMENT '就诊ID',
    order_id        BIGINT          DEFAULT NULL             COMMENT '关联回医嘱ID',
    exam_id         BIGINT          NOT NULL                 COMMENT '检查项目ID',
    order_time      DATETIME        NOT NULL                 COMMENT '申请时间',
    doctor_id       BIGINT          NOT NULL                 COMMENT '申请医生ID',
    is_stat         TINYINT(1)      DEFAULT 0                COMMENT '是否加急',
    imaging_status  VARCHAR(20)     DEFAULT '待检查'          COMMENT '状态(待检查/检查中/已报告)',
    exam_time       DATETIME        DEFAULT NULL             COMMENT '检查时间',
    report_time     DATETIME        DEFAULT NULL             COMMENT '报告时间',
    report_text     TEXT            DEFAULT NULL             COMMENT '报告内容',
    impression      TEXT            DEFAULT NULL             COMMENT '影像印象',
    radiologist_id  BIGINT          DEFAULT NULL             COMMENT '报告医师ID',
    created_at      DATETIME        DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME        DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (imaging_id),
    KEY idx_visit (visit_id),
    KEY idx_status (imaging_status)
) ENGINE=InnoDB COMMENT='影像检查申请与结果表';

-- ============================================================
-- 6. 护理与监护
-- ============================================================

-- 护理记录
DROP TABLE IF EXISTS ed_nursing_record;
CREATE TABLE ed_nursing_record (
    nursing_id      BIGINT          NOT NULL AUTO_INCREMENT  COMMENT '护理记录ID',
    visit_id        BIGINT          NOT NULL                 COMMENT '就诊ID',
    nurse_id        BIGINT          NOT NULL                 COMMENT '护士ID',
    record_time     DATETIME        NOT NULL                 COMMENT '记录时间',
    record_type     VARCHAR(20)     NOT NULL                 COMMENT '记录类型(常规/抢救/交接班/特殊)',
    hr              INT             DEFAULT NULL             COMMENT '心率',
    bp_systolic     INT             DEFAULT NULL             COMMENT '收缩压',
    bp_diastolic    INT             DEFAULT NULL             COMMENT '舒张压',
    temperature     DECIMAL(4,1)    DEFAULT NULL             COMMENT '体温',
    rr              INT             DEFAULT NULL             COMMENT '呼吸频率',
    spo2            INT             DEFAULT NULL             COMMENT '血氧',
    consciousness   VARCHAR(20)     DEFAULT NULL             COMMENT '意识',
    pain_score      TINYINT         DEFAULT NULL             COMMENT '疼痛评分',
    intake_ml       INT             DEFAULT NULL             COMMENT '入量(ml)',
    output_ml       INT             DEFAULT NULL             COMMENT '出量(ml)',
    iv_fluid        VARCHAR(100)    DEFAULT NULL             COMMENT '输液内容',
    nursing_content TEXT            DEFAULT NULL             COMMENT '护理内容',
    special_notes   TEXT            DEFAULT NULL             COMMENT '特殊情况',
    created_at      DATETIME        DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (nursing_id),
    KEY idx_visit (visit_id),
    KEY idx_time (record_time)
) ENGINE=InnoDB COMMENT='护理记录表';

-- ============================================================
-- 7. 抢救记录
-- ============================================================

DROP TABLE IF EXISTS ed_rescue_record;
CREATE TABLE ed_rescue_record (
    rescue_id       BIGINT          NOT NULL AUTO_INCREMENT  COMMENT '抢救记录ID',
    visit_id        BIGINT          NOT NULL                 COMMENT '就诊ID',
    rescue_start    DATETIME        NOT NULL                 COMMENT '抢救开始时间',
    rescue_end      DATETIME        DEFAULT NULL             COMMENT '抢救结束时间',
    rescue_duration INT             DEFAULT NULL             COMMENT '抢救时长(分钟)',
    rescue_leader   BIGINT          NOT NULL                 COMMENT '抢救负责人ID',
    rescue_team     JSON            DEFAULT NULL             COMMENT '抢救团队[staff_id,...]',
    arrest_type     VARCHAR(30)     DEFAULT NULL             COMMENT '心脏骤停类型(室颤/无脉性电活动/心电静止)',
    cpr_flag        TINYINT(1)      DEFAULT 0                COMMENT '是否心肺复苏',
    cpr_start       DATETIME        DEFAULT NULL             COMMENT 'CPR开始时间',
    cpr_duration    INT             DEFAULT NULL             COMMENT 'CPR时长(分钟)',
    defibrillation  JSON            DEFAULT NULL             COMMENT '除颤记录[{time,power,type}]',
    airway_type     VARCHAR(20)     DEFAULT NULL             COMMENT '气道管理方式(气管插管/喉罩/球囊面罩)',
    medication      JSON            DEFAULT NULL             COMMENT '抢救用药[{med,time,dose,route}]',
    outcome         VARCHAR(20)     DEFAULT NULL             COMMENT '抢救结果(成功/失败/死亡)',
    rescue_summary  TEXT            DEFAULT NULL             COMMENT '抢救经过摘要',
    created_at      DATETIME        DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (rescue_id),
    KEY idx_visit (visit_id),
    KEY idx_start (rescue_start)
) ENGINE=InnoDB COMMENT='抢救记录表';

-- ============================================================
-- 8. 留观管理
-- ============================================================

DROP TABLE IF EXISTS ed_observation;
CREATE TABLE ed_observation (
    obs_id          BIGINT          NOT NULL AUTO_INCREMENT  COMMENT '留观ID',
    visit_id        BIGINT          NOT NULL                 COMMENT '就诊ID',
    bed_id          BIGINT          DEFAULT NULL             COMMENT '留观床位ID',
    obs_start       DATETIME        NOT NULL                 COMMENT '留观开始时间',
    obs_end         DATETIME        DEFAULT NULL             COMMENT '留观结束时间',
    obs_duration    INT             DEFAULT NULL             COMMENT '留观时长(小时)',
    obs_reason      VARCHAR(200)    DEFAULT NULL             COMMENT '留观原因',
    reassess_count  INT             DEFAULT 0                COMMENT '复评次数',
    outcome         VARCHAR(20)     DEFAULT NULL             COMMENT '留观去向(离院/住院/转院)',
    dest_dept       VARCHAR(50)     DEFAULT NULL             COMMENT '转入科室',
    dest_ward       VARCHAR(50)     DEFAULT NULL             COMMENT '转入病区',
    created_at      DATETIME        DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (obs_id),
    KEY idx_visit (visit_id),
    KEY idx_bed (bed_id)
) ENGINE=InnoDB COMMENT='留观管理表';

-- ============================================================
-- 9. 绿色通道
-- ============================================================

DROP TABLE IF EXISTS ed_green_channel;
CREATE TABLE ed_green_channel (
    channel_id      BIGINT          NOT NULL AUTO_INCREMENT  COMMENT '通道ID',
    visit_id        BIGINT          NOT NULL                 COMMENT '就诊ID',
    channel_type    VARCHAR(20)     NOT NULL                 COMMENT '通道类型(胸痛/卒中/创伤/危重孕产妇/危重新生儿)',
    activate_time   DATETIME        NOT NULL                 COMMENT '启动时间',
    activate_doctor BIGINT          NOT NULL                 COMMENT '启动医生ID',
    door_to_ecg     INT             DEFAULT NULL             COMMENT '进门到心电图(秒)',
    door_to_needle  INT             DEFAULT NULL             COMMENT '进门到溶栓(秒)',
    door_to_balloon INT             DEFAULT NULL             COMMENT '进门到球囊(秒)',
    door_to_ct      INT             DEFAULT NULL             COMMENT '进门到CT(秒)',
    door_to_surgery INT             DEFAULT NULL             COMMENT '进门到手术(秒)',
    target_met      TINYINT(1)      DEFAULT NULL             COMMENT '是否达标',
    channel_outcome VARCHAR(30)     DEFAULT NULL             COMMENT '结局',
    created_at      DATETIME        DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (channel_id),
    KEY idx_visit (visit_id),
    KEY idx_type (channel_type)
) ENGINE=InnoDB COMMENT='绿色通道表';

-- ============================================================
-- 10. 质控与统计
-- ============================================================

DROP TABLE IF EXISTS ed_quality_indicator;
CREATE TABLE ed_quality_indicator (
    indicator_id    BIGINT          NOT NULL AUTO_INCREMENT  COMMENT '指标ID',
    visit_id        BIGINT          DEFAULT NULL             COMMENT '关联就诊ID(可为空表示汇总)',
    indicator_date  DATE            NOT NULL                 COMMENT '统计日期',
    indicator_name  VARCHAR(100)    NOT NULL                 COMMENT '指标名称',
    indicator_value DECIMAL(12,4)   DEFAULT NULL             COMMENT '指标值',
    indicator_unit  VARCHAR(20)     DEFAULT NULL             COMMENT '指标单位',
    target_value    DECIMAL(12,4)   DEFAULT NULL             COMMENT '目标值',
    is_met          TINYINT(1)      DEFAULT NULL             COMMENT '是否达标',
    created_at      DATETIME        DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (indicator_id),
    KEY idx_date (indicator_date),
    KEY idx_name (indicator_name)
) ENGINE=InnoDB COMMENT='质控指标表';

-- ============================================================
-- 11. 系统操作日志
-- ============================================================

DROP TABLE IF EXISTS sys_audit_log;
CREATE TABLE sys_audit_log (
    log_id          BIGINT          NOT NULL AUTO_INCREMENT  COMMENT '日志ID',
    staff_id        BIGINT          DEFAULT NULL             COMMENT '操作人ID',
    action          VARCHAR(50)     NOT NULL                 COMMENT '操作动作',
    target_table    VARCHAR(50)     DEFAULT NULL             COMMENT '目标表',
    target_id       BIGINT          DEFAULT NULL             COMMENT '目标记录ID',
    old_value       JSON            DEFAULT NULL             COMMENT '修改前值',
    new_value       JSON            DEFAULT NULL             COMMENT '修改后值',
    ip_address      VARCHAR(45)     DEFAULT NULL             COMMENT 'IP地址',
    created_at      DATETIME        DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (log_id),
    KEY idx_staff (staff_id),
    KEY idx_action (action),
    KEY idx_time (created_at)
) ENGINE=InnoDB COMMENT='系统操作日志表';
