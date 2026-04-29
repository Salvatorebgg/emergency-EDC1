# 项目记忆 - EDCli

## 项目：急诊科 EDC 电子数据采集系统
- 创建日期：2026-04-23
- 位置：d:\BaiduSyncdisk\document\workdocument\EDCli
- MySQL：localhost:3306, root, 5311600wang, 数据库名 ed_emergency
- MySQL路径：C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe
- API：Python Flask, 端口5000, 文件 api/app.py
- 前端：web/index.html（深色主题单页应用）

## 数据库架构
- 19张表：5张字典表 + 5张基础表 + 9张业务表
- 6个视图：v_ed_visit_full(核心)、v_bed_status、v_triage_queue、v_waiting_queue、v_lab_results、v_ed_dashboard
- 6个存储过程：sp_register_ed_visit(含自动预分诊)、sp_triage_assess、sp_assign_bed、sp_discharge_patient、sp_daily_report、sp_zone_statistics

## 种子数据
- 18个科室、19名医护、36条ICD-10诊断、28种药品、34个检查项目
- 27张床位（红区5/黄区8/绿区14）、12名患者、10条就诊记录
- 含完整的医嘱、检验、影像、护理、绿色通道、质控指标数据

## 踩坑经验
- MySQL JSON字段中 NULL 不是合法JSON值，要用小写 null
- 分诊评估表 INSERT 时列数要精确匹配（brief_history 字段不要漏）
- Google Fonts 在国内被墙，会导致页面完全卡住不渲染——不要用 fonts.googleapis.com，改用系统字体或国内 CDN
- Flask debug=True 后台启动时 reloader 会出问题，生产/后台模式用 debug=False + threaded=True
- 前端必须通过 http://localhost:5000/ 访问，file:// 协议会因 CORS 阻止 API 请求
