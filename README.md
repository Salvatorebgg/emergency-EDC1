# 急诊科 EDC 电子数据采集系统

## 项目概述

模拟医院急诊科的电子数据采集（EDC）系统，覆盖急诊科完整业务流程：患者登记 → 分诊评估 → 就诊 → 检查检验 → 诊断处置 → 离科。

## 技术架构

| 层级 | 技术 | 说明 |
|------|------|------|
| 数据库 | MySQL 8.0 | 17张核心业务表 + 6个视图 + 6个存储过程 |
| API | Python Flask | RESTful API，端口 5000 |
| 前端 | HTML/CSS/JS | 单页应用，深色主题，实时刷新 |

## 数据库设计

### 核心表结构

| 表名 | 说明 |
|------|------|
| sys_department | 科室信息 |
| sys_staff | 医护人员 |
| sys_diagnosis_dict | 诊断字典(ICD-10) |
| sys_medicine_dict | 药品字典 |
| sys_exam_dict | 检查检验项目 |
| ed_bed | 急诊床位 |
| patient_info | 患者基本信息 |
| ed_visit | 就诊主记录 |
| ed_triage_assessment | 分诊评估 |
| ed_medical_record | 医生诊疗记录 |
| ed_order | 医嘱 |
| ed_lab_order | 检验申请与结果 |
| ed_imaging_order | 影像检查 |
| ed_nursing_record | 护理记录 |
| ed_rescue_record | 抢救记录 |
| ed_observation | 留观管理 |
| ed_green_channel | 绿色通道 |
| ed_quality_indicator | 质控指标 |
| sys_audit_log | 操作日志 |

## 启动方式

1. 初始化数据库：依次执行 sql/ 目录下的4个SQL文件
2. 启动 API：`python api/app.py`
3. 打开前端：浏览器访问 `web/index.html`

## 分诊级别

1级(红/濒危) → 2级(橙/危重) → 3级(黄/急症) → 4级(绿/非急) → 5级(蓝/非急诊)
