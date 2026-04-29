-- ============================================================
-- 急诊科 EDC 系统 - 视图与存储过程
-- ============================================================

USE ed_emergency;

-- ============================================================
-- 视图
-- ============================================================

-- 1. 急诊就诊综合视图(核心视图)
CREATE OR REPLACE VIEW v_ed_visit_full AS
SELECT 
    v.visit_id,
    v.visit_no,
    v.patient_id,
    p.patient_no,
    p.patient_name,
    p.gender,
    p.age,
    p.age_unit,
    p.phone,
    p.id_card_no,
    p.blood_type,
    p.allergy_history,
    p.past_history,
    v.visit_date,
    v.visit_time,
    v.arrival_mode,
    v.chief_complaint,
    v.triage_level,
    v.triage_color,
    v.triage_time,
    v.visit_status,
    v.outcome,
    v.icd_code,
    d1.icd_name AS main_diagnosis,
    v.icd_code2,
    d2.icd_name AS sub_diagnosis,
    s1.staff_name AS triage_nurse_name,
    s2.staff_name AS attending_doctor_name,
    b.bed_code,
    b.bed_zone,
    b.bed_type,
    v.is_green_channel,
    v.is_trauma,
    v.is_120_transfer,
    v.is_pediatric,
    v.outcome_time,
    TIMESTAMPDIFF(MINUTE, v.visit_time, IFNULL(v.outcome_time, NOW())) AS stay_minutes
FROM ed_visit v
LEFT JOIN patient_info p ON v.patient_id = p.patient_id
LEFT JOIN sys_diagnosis_dict d1 ON v.icd_code = d1.icd_code
LEFT JOIN sys_diagnosis_dict d2 ON v.icd_code2 = d2.icd_code
LEFT JOIN sys_staff s1 ON v.triage_nurse_id = s1.staff_id
LEFT JOIN sys_staff s2 ON v.attending_doctor_id = s2.staff_id
LEFT JOIN ed_bed b ON v.bed_id = b.bed_id;

-- 2. 床位状态视图
CREATE OR REPLACE VIEW v_bed_status AS
SELECT 
    b.bed_id,
    b.bed_code,
    b.bed_zone,
    b.bed_type,
    b.bed_status,
    b.has_monitor,
    b.has_ventilator,
    IF(b.bed_status = '占用', v.visit_no, NULL) AS current_visit_no,
    IF(b.bed_status = '占用', p.patient_name, NULL) AS current_patient,
    IF(b.bed_status = '占用', v.triage_level, NULL) AS triage_level,
    IF(b.bed_status = '占用', v.chief_complaint, NULL) AS chief_complaint,
    IF(b.bed_status = '占用', s.staff_name, NULL) AS attending_doctor
FROM ed_bed b
LEFT JOIN ed_visit v ON b.current_visit_id = v.visit_id AND b.bed_status = '占用'
LEFT JOIN patient_info p ON v.patient_id = p.patient_id
LEFT JOIN sys_staff s ON v.attending_doctor_id = s.staff_id
ORDER BY 
    CASE b.bed_zone WHEN '红区' THEN 1 WHEN '黄区' THEN 2 WHEN '绿区' THEN 3 END,
    b.sort_order;

-- 3. 分诊待处理队列
CREATE OR REPLACE VIEW v_triage_queue AS
SELECT 
    v.visit_id,
    v.visit_no,
    v.patient_id,
    p.patient_name,
    p.gender,
    p.age,
    p.age_unit,
    v.visit_time,
    v.chief_complaint,
    v.arrival_mode,
    TIMESTAMPDIFF(MINUTE, v.visit_time, NOW()) AS wait_minutes
FROM ed_visit v
LEFT JOIN patient_info p ON v.patient_id = p.patient_id
WHERE v.visit_status = '分诊中'
ORDER BY v.visit_time;

-- 4. 候诊队列视图
CREATE OR REPLACE VIEW v_waiting_queue AS
SELECT 
    v.visit_id,
    v.visit_no,
    p.patient_name,
    p.gender,
    p.age,
    v.triage_level,
    v.triage_color,
    v.chief_complaint,
    v.triage_time,
    TIMESTAMPDIFF(MINUTE, v.triage_time, NOW()) AS wait_minutes
FROM ed_visit v
LEFT JOIN patient_info p ON v.patient_id = p.patient_id
WHERE v.visit_status = '候诊'
ORDER BY v.triage_level ASC, v.triage_time ASC;

-- 5. 检验结果视图
CREATE OR REPLACE VIEW v_lab_results AS
SELECT 
    l.lab_id,
    l.visit_id,
    v.visit_no,
    p.patient_name,
    e.exam_name,
    e.exam_category,
    l.order_time,
    l.is_stat,
    l.lab_status,
    l.result_value,
    l.result_unit,
    l.result_flag,
    l.result_text,
    l.reference_range,
    l.report_time,
    TIMESTAMPDIFF(MINUTE, l.order_time, IFNULL(l.report_time, NOW())) AS turnaround_minutes
FROM ed_lab_order l
LEFT JOIN ed_visit v ON l.visit_id = v.visit_id
LEFT JOIN patient_info p ON v.patient_id = p.patient_id
LEFT JOIN sys_exam_dict e ON l.exam_id = e.exam_id;

-- 6. 急诊大屏统计视图
CREATE OR REPLACE VIEW v_ed_dashboard AS
SELECT
    (SELECT COUNT(*) FROM ed_visit WHERE visit_date = CURDATE()) AS total_visits_today,
    (SELECT COUNT(*) FROM ed_visit WHERE visit_status IN ('分诊中','候诊','就诊中','观察中','处置中') AND visit_date = CURDATE()) AS active_visits,
    (SELECT COUNT(*) FROM ed_visit WHERE visit_status = '候诊' AND visit_date = CURDATE()) AS waiting_count,
    (SELECT COUNT(*) FROM ed_visit WHERE triage_level = 1 AND visit_status NOT IN ('已离院','已转院') AND visit_date = CURDATE()) AS level1_count,
    (SELECT COUNT(*) FROM ed_visit WHERE triage_level = 2 AND visit_status NOT IN ('已离院','已转院') AND visit_date = CURDATE()) AS level2_count,
    (SELECT COUNT(*) FROM ed_bed WHERE bed_status = '空闲') AS beds_available,
    (SELECT COUNT(*) FROM ed_bed WHERE bed_status = '占用') AS beds_occupied,
    (SELECT COUNT(*) FROM ed_bed WHERE bed_zone = '红区' AND bed_status = '空闲') AS red_beds_available,
    (SELECT COUNT(*) FROM ed_bed WHERE bed_zone = '红区' AND bed_status = '占用') AS red_beds_occupied,
    (SELECT COUNT(*) FROM ed_lab_order WHERE lab_status = '待采集' OR lab_status = '检验中') AS pending_labs,
    (SELECT COUNT(*) FROM ed_imaging_order WHERE imaging_status = '待检查' OR imaging_status = '检查中') AS pending_imaging,
    (SELECT COUNT(*) FROM ed_visit WHERE is_green_channel = 1 AND visit_status NOT IN ('已离院','已转院') AND visit_date = CURDATE()) AS green_channel_active;

-- ============================================================
-- 存储过程
-- ============================================================

-- 1. 患者登记并创建急诊就诊
DELIMITER //
CREATE PROCEDURE sp_register_ed_visit(
    IN p_patient_no     VARCHAR(20),
    IN p_id_card        VARCHAR(18),
    IN p_name           VARCHAR(50),
    IN p_gender         CHAR(1),
    IN p_birth_date     DATE,
    IN p_age            INT,
    IN p_age_unit       VARCHAR(5),
    IN p_phone          VARCHAR(20),
    IN p_address        VARCHAR(200),
    IN p_emerg_contact  VARCHAR(50),
    IN p_emerg_phone    VARCHAR(20),
    IN p_blood_type     VARCHAR(5),
    IN p_allergy        TEXT,
    IN p_past_history   TEXT,
    IN p_insurance      VARCHAR(20),
    IN p_arrival_mode   VARCHAR(20),
    IN p_chief_complaint VARCHAR(500),
    IN p_present_illness TEXT,
    IN p_nurse_id       BIGINT
)
BEGIN
    DECLARE v_patient_id BIGINT;
    DECLARE v_visit_no VARCHAR(20);
    DECLARE v_triage_level TINYINT;
    DECLARE v_triage_color VARCHAR(10);
    
    -- 查找或创建患者
    SELECT patient_id INTO v_patient_id FROM patient_info WHERE patient_no = p_patient_no LIMIT 1;
    
    IF v_patient_id IS NULL THEN
        INSERT INTO patient_info (patient_no, id_card_no, patient_name, gender, birth_date, age, age_unit, phone, address, emergency_contact, emergency_phone, blood_type, allergy_history, past_history, insurance_type)
        VALUES (p_patient_no, p_id_card, p_name, p_gender, p_birth_date, p_age, p_age_unit, p_phone, p_address, p_emerg_contact, p_emerg_phone, p_blood_type, p_allergy, p_past_history, p_insurance);
        SET v_patient_id = LAST_INSERT_ID();
    END IF;
    
    -- 生成就诊流水号
    SET v_visit_no = CONCAT('ED', DATE_FORMAT(CURDATE(), '%Y%m%d'), LPAD(
        (SELECT IFNULL(MAX(CAST(SUBSTRING(visit_no, -3) AS UNSIGNED)), 0) + 1 
         FROM ed_visit WHERE visit_date = CURDATE()), 3, '0'));
    
    -- 自动预分诊(根据主诉关键词初步判定)
    SET v_triage_level = 3;
    SET v_triage_color = '黄';
    
    IF p_chief_complaint REGEXP '胸痛|心悸|心脏骤停|呼吸心跳停止|意识丧失|大出血' THEN
        SET v_triage_level = 1; SET v_triage_color = '红';
    ELSEIF p_chief_complaint REGEXP '气促|呼吸困难|剧烈腹痛|意识模糊|高热|抽搐|中风|偏瘫|车祸|坠落|中毒' THEN
        SET v_triage_level = 2; SET v_triage_color = '橙';
    ELSEIF p_chief_complaint REGEXP '发热|腹痛|腹泻|头晕|呕吐|腰痛|皮疹' THEN
        SET v_triage_level = 3; SET v_triage_color = '黄';
    ELSEIF p_chief_complaint REGEXP '扭伤|擦伤|轻微疼痛|换药|拆线|复查' THEN
        SET v_triage_level = 4; SET v_triage_color = '绿';
    ELSE
        SET v_triage_level = 5; SET v_triage_color = '蓝';
    END IF;
    
    -- 创建就诊记录
    INSERT INTO ed_visit (visit_no, patient_id, visit_date, visit_time, arrival_mode, chief_complaint, present_illness, triage_level, triage_color, triage_nurse_id, triage_time, visit_status)
    VALUES (v_visit_no, v_patient_id, CURDATE(), NOW(), p_arrival_mode, p_chief_complaint, p_present_illness, v_triage_level, v_triage_color, p_nurse_id, NOW(), '分诊中');
    
    SELECT LAST_INSERT_ID() AS visit_id, v_visit_no AS visit_no, v_triage_level AS triage_level, v_triage_color AS triage_color;
END //
DELIMITER ;

-- 2. 分诊评估
DELIMITER //
CREATE PROCEDURE sp_triage_assess(
    IN p_visit_id       BIGINT,
    IN p_nurse_id       BIGINT,
    IN p_consciousness  VARCHAR(20),
    IN p_pain_score     TINYINT,
    IN p_hr             INT,
    IN p_bp_sys         INT,
    IN p_bp_dia         INT,
    IN p_temp           DECIMAL(4,1),
    IN p_rr             INT,
    IN p_spo2           INT,
    IN p_weight         DECIMAL(5,1),
    IN p_fall_risk      VARCHAR(10),
    IN p_triage_level   TINYINT,
    IN p_triage_category VARCHAR(50),
    IN p_brief_history  TEXT
)
BEGIN
    DECLARE v_triage_color VARCHAR(10);
    DECLARE v_patient_id BIGINT;
    
    -- 根据分诊级别设置颜色
    SET v_triage_color = CASE p_triage_level
        WHEN 1 THEN '红' WHEN 2 THEN '橙' WHEN 3 THEN '黄' WHEN 4 THEN '绿' WHEN 5 THEN '蓝'
    END;
    
    -- 获取患者ID
    SELECT patient_id INTO v_patient_id FROM ed_visit WHERE visit_id = p_visit_id;
    
    -- 创建分诊评估记录
    INSERT INTO ed_triage_assessment (visit_id, assess_time, nurse_id, consciousness, pain_score, hr, bp_systolic, bp_diastolic, temperature, rr, spo2, weight, fall_risk, triage_level, triage_category, chief_complaint, brief_history)
    SELECT p_visit_id, NOW(), p_nurse_id, p_consciousness, p_pain_score, p_hr, p_bp_sys, p_bp_dia, p_temp, p_rr, p_spo2, p_weight, p_fall_risk, p_triage_level, p_triage_category, chief_complaint, p_brief_history
    FROM ed_visit WHERE visit_id = p_visit_id;
    
    -- 更新就诊记录
    UPDATE ed_visit SET 
        triage_level = p_triage_level,
        triage_color = v_triage_color,
        triage_time = NOW(),
        triage_nurse_id = p_nurse_id,
        triage_vitals = JSON_OBJECT('HR', p_hr, 'BP_S', p_bp_sys, 'BP_D', p_bp_dia, 'Temp', p_temp, 'RR', p_rr, 'SpO2', p_spo2, 'Pain', p_pain_score),
        visit_status = '候诊'
    WHERE visit_id = p_visit_id;
    
    SELECT p_visit_id AS visit_id, p_triage_level AS triage_level, v_triage_color AS triage_color, '候诊' AS new_status;
END //
DELIMITER ;

-- 3. 分配床位
DELIMITER //
CREATE PROCEDURE sp_assign_bed(
    IN p_visit_id   BIGINT,
    IN p_bed_id     BIGINT
)
BEGIN
    DECLARE v_old_bed_id BIGINT;
    
    -- 获取当前床位
    SELECT bed_id INTO v_old_bed_id FROM ed_visit WHERE visit_id = p_visit_id;
    
    -- 释放旧床位
    IF v_old_bed_id IS NOT NULL THEN
        UPDATE ed_bed SET bed_status = '清洁中', current_visit_id = NULL WHERE bed_id = v_old_bed_id;
    END IF;
    
    -- 占用新床位
    UPDATE ed_bed SET bed_status = '占用', current_visit_id = p_visit_id WHERE bed_id = p_bed_id;
    
    -- 更新就诊记录
    UPDATE ed_visit SET bed_id = p_bed_id, visit_status = '就诊中' WHERE visit_id = p_visit_id;
    
    SELECT p_visit_id AS visit_id, p_bed_id AS bed_id, '就诊中' AS new_status;
END //
DELIMITER ;

-- 4. 患者离科
DELIMITER //
CREATE PROCEDURE sp_discharge_patient(
    IN p_visit_id   BIGINT,
    IN p_outcome    VARCHAR(20),
    IN p_dest_dept  VARCHAR(50),
    IN p_icd_code   VARCHAR(10)
)
BEGIN
    DECLARE v_bed_id BIGINT;
    
    -- 获取床位
    SELECT bed_id INTO v_bed_id FROM ed_visit WHERE visit_id = p_visit_id;
    
    -- 释放床位
    IF v_bed_id IS NOT NULL THEN
        UPDATE ed_bed SET bed_status = '清洁中', current_visit_id = NULL WHERE bed_id = v_bed_id;
    END IF;
    
    -- 更新就诊记录
    UPDATE ed_visit SET 
        visit_status = CASE p_outcome WHEN '死亡' THEN '死亡' ELSE '已离院' END,
        outcome = p_outcome,
        outcome_time = NOW(),
        icd_code = IFNULL(p_icd_code, icd_code)
    WHERE visit_id = p_visit_id;
    
    SELECT p_visit_id AS visit_id, p_outcome AS outcome, NOW() AS outcome_time;
END //
DELIMITER ;

-- 5. 每日统计报表
DELIMITER //
CREATE PROCEDURE sp_daily_report(
    IN p_date DATE
)
BEGIN
    SELECT 
        COUNT(*) AS total_visits,
        SUM(CASE WHEN triage_level = 1 THEN 1 ELSE 0 END) AS level1_count,
        SUM(CASE WHEN triage_level = 2 THEN 1 ELSE 0 END) AS level2_count,
        SUM(CASE WHEN triage_level = 3 THEN 1 ELSE 0 END) AS level3_count,
        SUM(CASE WHEN triage_level = 4 THEN 1 ELSE 0 END) AS level4_count,
        SUM(CASE WHEN triage_level = 5 THEN 1 ELSE 0 END) AS level5_count,
        SUM(CASE WHEN outcome = '离院回家' THEN 1 ELSE 0 END) AS discharged_home,
        SUM(CASE WHEN outcome = '住院' THEN 1 ELSE 0 END) AS admitted,
        SUM(CASE WHEN outcome = '转院' THEN 1 ELSE 0 END) AS transferred,
        SUM(CASE WHEN outcome = '死亡' THEN 1 ELSE 0 END) AS expired,
        SUM(CASE WHEN is_green_channel = 1 THEN 1 ELSE 0 END) AS green_channel_count,
        SUM(CASE WHEN is_120_transfer = 1 THEN 1 ELSE 0 END) AS transfer_120_count,
        SUM(CASE WHEN is_trauma = 1 THEN 1 ELSE 0 END) AS trauma_count,
        AVG(TIMESTAMPDIFF(MINUTE, visit_time, outcome_time)) AS avg_stay_minutes
    FROM ed_visit 
    WHERE visit_date = p_date;
END //
DELIMITER ;

-- 6. 急诊分区统计
DELIMITER //
CREATE PROCEDURE sp_zone_statistics()
BEGIN
    SELECT 
        b.bed_zone,
        COUNT(*) AS total_beds,
        SUM(CASE WHEN b.bed_status = '占用' THEN 1 ELSE 0 END) AS occupied,
        SUM(CASE WHEN b.bed_status = '空闲' THEN 1 ELSE 0 END) AS available,
        SUM(CASE WHEN b.bed_status = '清洁中' THEN 1 ELSE 0 END) AS cleaning,
        SUM(CASE WHEN b.bed_status = '维修' THEN 1 ELSE 0 END) AS maintenance,
        ROUND(SUM(CASE WHEN b.bed_status = '占用' THEN 1 ELSE 0 END) / COUNT(*) * 100, 1) AS occupancy_rate
    FROM ed_bed b
    GROUP BY b.bed_zone
    ORDER BY CASE b.bed_zone WHEN '红区' THEN 1 WHEN '黄区' THEN 2 WHEN '绿区' THEN 3 END;
END //
DELIMITER ;
