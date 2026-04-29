#!/usr/bin/env python
"""Generate realistic phase-3 demo data for the ED EDC system.

This script is additive: it preserves existing demo records and fills the
database up to the requested target size.
"""

from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

import pymysql


DB_CONFIG = {
    "host": "localhost",
    "port": 3306,
    "user": "root",
    "password": "5311600wang",
    "database": "ed_emergency",
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
    "autocommit": False,
}


TRIAGE_COLORS = {1: "红", 2: "橙", 3: "黄", 4: "绿", 5: "蓝"}
ACTIVE_STATUSES = ["候诊", "就诊中", "观察中", "处置中"]


SURNAME_POOL = list(
    "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜谢邹喻柏水窦章云苏潘葛范彭郎鲁韦昌马苗凤花方俞任袁柳鲍史唐费廉岑薛雷贺倪汤滕殷罗毕郝邬安常乐于时傅皮卞齐康伍余元顾孟平黄和穆萧尹"
)
NAME_POOL = [
    "伟", "芳", "军", "敏", "静", "磊", "涛", "艳", "强", "鹏", "涛", "婷", "勇", "娜", "超", "杰",
    "瑞", "楠", "佳", "晨", "昊", "雪", "琳", "鑫", "博", "媛", "珊", "晨", "俊", "欣", "浩", "露",
    "凡", "博", "然", "宇", "峰", "倩", "蕾", "琪", "健", "璐", "轩", "婧", "嘉", "宁", "航", "茜",
]


@dataclass(frozen=True)
class Scenario:
    key: str
    diagnosis: str
    icd: str
    complaints: tuple[str, ...]
    histories: tuple[str, ...]
    triage_levels: tuple[int, ...]
    arrival_modes: tuple[str, ...]
    green_type: str | None
    green_prob: float
    rescue_prob: float
    observation_prob: float
    trauma: bool
    pediatric: bool
    lab_names: tuple[str, ...]
    imaging_names: tuple[str, ...]
    order_templates: tuple[dict, ...]
    outcome_weights: tuple[tuple[str, int], ...]
    past_histories: tuple[str, ...]
    allergies: tuple[str, ...]


SCENARIOS = [
    Scenario(
        key="chest_pain",
        diagnosis="急性冠脉综合征",
        icd="I20.0",
        complaints=("持续胸痛2小时", "胸闷胸痛伴大汗1小时", "胸骨后压榨样疼痛90分钟"),
        histories=(
            "活动后出现胸骨后压榨样疼痛，向左肩背放射，伴恶心大汗，含服硝酸甘油缓解不佳。",
            "静息状态下突发胸闷胸痛，伴濒死感与出汗，家属送至急诊。",
        ),
        triage_levels=(1, 2, 2),
        arrival_modes=("120急救", "步行", "轮椅"),
        green_type="胸痛",
        green_prob=0.75,
        rescue_prob=0.12,
        observation_prob=0.35,
        trauma=False,
        pediatric=False,
        lab_names=("血常规", "肌钙蛋白I", "CK-MB", "凝血四项", "血糖"),
        imaging_names=("胸部CT平扫",),
        order_templates=(
            {"type": "药品", "category": "临时", "content": "阿司匹林肠溶片 300mg 口服", "dosage": "300mg", "frequency": "STAT", "route": "口服", "stat": 1},
            {"type": "药品", "category": "临时", "content": "硝酸甘油 5mg 静脉泵入", "dosage": "5mg", "frequency": "持续", "route": "静脉泵入", "stat": 1},
            {"type": "检验", "category": "临时", "content": "心肌标志物 + 凝血四项", "dosage": None, "frequency": "STAT", "route": None, "stat": 1},
            {"type": "检查", "category": "临时", "content": "胸部CT平扫", "dosage": None, "frequency": "STAT", "route": None, "stat": 1},
        ),
        outcome_weights=(("离院回家", 25), ("住院", 55), ("转院", 15), ("死亡", 5)),
        past_histories=("高血压病10年", "冠心病支架术后", "2型糖尿病5年"),
        allergies=("青霉素过敏", "无特殊过敏史"),
    ),
    Scenario(
        key="stroke",
        diagnosis="急性脑梗死",
        icd="I63.9",
        complaints=("言语不清伴右侧肢体无力1小时", "口角歪斜30分钟", "突发偏瘫伴意识模糊45分钟"),
        histories=(
            "发病前无明显诱因，突然出现言语含糊，右侧肢体抬举困难，家属立即拨打120。",
            "晨起后出现口角歪斜、行走不稳，伴轻度意识模糊。",
        ),
        triage_levels=(1, 1, 2),
        arrival_modes=("120急救", "平车"),
        green_type="卒中",
        green_prob=0.85,
        rescue_prob=0.10,
        observation_prob=0.15,
        trauma=False,
        pediatric=False,
        lab_names=("血常规", "凝血四项", "急诊生化", "血糖"),
        imaging_names=("头颅CT平扫", "头颅CTA"),
        order_templates=(
            {"type": "检验", "category": "临时", "content": "血常规 + 凝血四项 + 急诊生化", "dosage": None, "frequency": "STAT", "route": None, "stat": 1},
            {"type": "检查", "category": "临时", "content": "头颅CT平扫", "dosage": None, "frequency": "STAT", "route": None, "stat": 1},
            {"type": "检查", "category": "临时", "content": "头颅CTA", "dosage": None, "frequency": "STAT", "route": None, "stat": 1},
        ),
        outcome_weights=(("离院回家", 5), ("住院", 70), ("转院", 20), ("死亡", 5)),
        past_histories=("高血压病12年", "房颤病史", "既往脑梗死后遗症"),
        allergies=("碘造影剂过敏", "无特殊过敏史"),
    ),
    Scenario(
        key="trauma",
        diagnosis="多发伤",
        icd="T14.9",
        complaints=("车祸伤后胸腹痛30分钟", "高处坠落伤1小时", "刀割伤伴出血20分钟"),
        histories=(
            "交通事故后出现胸腹部疼痛，伴右下肢活动受限，现场已简易包扎。",
            "工作时高处坠落，落地后出现胸背痛，头部无明显出血。",
        ),
        triage_levels=(1, 2, 2),
        arrival_modes=("120急救", "平车"),
        green_type="创伤",
        green_prob=0.80,
        rescue_prob=0.18,
        observation_prob=0.22,
        trauma=True,
        pediatric=False,
        lab_names=("血常规", "凝血四项", "血型鉴定", "交叉配血", "急诊生化"),
        imaging_names=("胸部CT平扫", "腹部CT平扫", "四肢X线"),
        order_templates=(
            {"type": "药品", "category": "临时", "content": "乳酸林格液 500ml 快速补液", "dosage": "500ml", "frequency": "STAT", "route": "静脉滴注", "stat": 1},
            {"type": "药品", "category": "临时", "content": "曲马多 100mg 肌注", "dosage": "100mg", "frequency": "STAT", "route": "肌内注射", "stat": 1},
            {"type": "检查", "category": "临时", "content": "胸腹部CT + 四肢X线", "dosage": None, "frequency": "STAT", "route": None, "stat": 1},
        ),
        outcome_weights=(("离院回家", 8), ("住院", 58), ("转院", 28), ("死亡", 6)),
        past_histories=("无特殊既往史", "高血压病史"),
        allergies=("头孢过敏", "无特殊过敏史"),
    ),
    Scenario(
        key="abdomen",
        diagnosis="急性腹痛待查",
        icd="R10.4",
        complaints=("腹痛伴恶心呕吐6小时", "右下腹痛加重4小时", "上腹痛向后背放射3小时"),
        histories=(
            "进食后出现持续性腹痛，伴恶心呕吐，无黑便。",
            "腹痛由脐周转移至右下腹，行走震动时加重。",
        ),
        triage_levels=(2, 3, 3),
        arrival_modes=("步行", "轮椅"),
        green_type=None,
        green_prob=0.0,
        rescue_prob=0.03,
        observation_prob=0.42,
        trauma=False,
        pediatric=False,
        lab_names=("血常规", "急诊生化", "淀粉酶", "C反应蛋白"),
        imaging_names=("腹部CT平扫", "急诊超声"),
        order_templates=(
            {"type": "药品", "category": "临时", "content": "昂丹司琼 4mg 静推", "dosage": "4mg", "frequency": "STAT", "route": "静脉注射", "stat": 0},
            {"type": "药品", "category": "临时", "content": "布洛芬缓释胶囊 0.3g 口服", "dosage": "0.3g", "frequency": "STAT", "route": "口服", "stat": 0},
            {"type": "检查", "category": "临时", "content": "腹部CT平扫", "dosage": None, "frequency": "STAT", "route": None, "stat": 0},
        ),
        outcome_weights=(("离院回家", 40), ("住院", 45), ("转院", 12), ("死亡", 3)),
        past_histories=("胆囊结石病史", "慢性胃炎", "无特殊既往史"),
        allergies=("无特殊过敏史", "青霉素过敏"),
    ),
    Scenario(
        key="dyspnea",
        diagnosis="急性呼吸困难",
        icd="R06.0",
        complaints=("呼吸困难加重半天", "喘息伴咳痰2天", "夜间端坐呼吸3小时"),
        histories=(
            "受凉后出现咳嗽咳黄痰，呼吸困难逐渐加重，平卧困难。",
            "既往慢阻肺基础上本次呼吸困难明显，活动后不能缓解。",
        ),
        triage_levels=(1, 2, 2),
        arrival_modes=("120急救", "轮椅", "步行"),
        green_type=None,
        green_prob=0.0,
        rescue_prob=0.08,
        observation_prob=0.46,
        trauma=False,
        pediatric=False,
        lab_names=("血常规", "血气分析", "C反应蛋白", "BNP/NT-proBNP"),
        imaging_names=("胸部CT平扫", "胸部X线"),
        order_templates=(
            {"type": "药品", "category": "长期", "content": "左氧氟沙星 0.5g 静滴", "dosage": "0.5g", "frequency": "QD", "route": "静脉滴注", "stat": 0},
            {"type": "药品", "category": "临时", "content": "沙丁胺醇雾化吸入", "dosage": "1次", "frequency": "STAT", "route": "雾化吸入", "stat": 1},
            {"type": "检查", "category": "临时", "content": "胸部CT平扫", "dosage": None, "frequency": "STAT", "route": None, "stat": 1},
        ),
        outcome_weights=(("离院回家", 18), ("住院", 60), ("转院", 18), ("死亡", 4)),
        past_histories=("慢阻肺10年", "支气管哮喘", "慢性心衰病史"),
        allergies=("无特殊过敏史", "头孢过敏"),
    ),
    Scenario(
        key="fever",
        diagnosis="发热待查",
        icd="R50.9",
        complaints=("发热伴寒战1天", "高热伴咳嗽2天", "发热伴乏力腹泻1天"),
        histories=(
            "今日体温最高39.4℃，伴咽痛和全身酸痛，口服退热药后反复发热。",
            "高热伴咳嗽咳痰，精神一般，进食减少。",
        ),
        triage_levels=(3, 3, 4),
        arrival_modes=("步行", "轮椅"),
        green_type=None,
        green_prob=0.0,
        rescue_prob=0.01,
        observation_prob=0.18,
        trauma=False,
        pediatric=False,
        lab_names=("血常规", "C反应蛋白", "降钙素原", "急诊生化"),
        imaging_names=("胸部X线",),
        order_templates=(
            {"type": "药品", "category": "临时", "content": "对乙酰氨基酚 0.5g 口服", "dosage": "0.5g", "frequency": "STAT", "route": "口服", "stat": 0},
            {"type": "药品", "category": "长期", "content": "0.9%NS 250ml 静滴", "dosage": "250ml", "frequency": "QD", "route": "静脉滴注", "stat": 0},
            {"type": "检验", "category": "临时", "content": "血常规 + CRP + PCT", "dosage": None, "frequency": "STAT", "route": None, "stat": 0},
        ),
        outcome_weights=(("离院回家", 72), ("住院", 18), ("转院", 8), ("死亡", 2)),
        past_histories=("高血压病史", "无特殊既往史"),
        allergies=("无特殊过敏史", "青霉素过敏"),
    ),
    Scenario(
        key="pediatric_fever",
        diagnosis="小儿上呼吸道感染",
        icd="J06.9",
        complaints=("发热伴咳嗽1天", "儿童高热39℃半天", "咽痛伴流涕1天"),
        histories=(
            "患儿发热伴流涕咳嗽，精神欠佳，无抽搐，家长携来急诊。",
            "今日午后高热，伴咽痛，食欲下降，无呕吐腹泻。",
        ),
        triage_levels=(3, 4, 4),
        arrival_modes=("步行",),
        green_type=None,
        green_prob=0.0,
        rescue_prob=0.0,
        observation_prob=0.10,
        trauma=False,
        pediatric=True,
        lab_names=("血常规", "C反应蛋白"),
        imaging_names=(),
        order_templates=(
            {"type": "药品", "category": "临时", "content": "布洛芬混悬液 5ml 口服", "dosage": "5ml", "frequency": "STAT", "route": "口服", "stat": 0},
            {"type": "检验", "category": "临时", "content": "血常规 + CRP", "dosage": None, "frequency": "STAT", "route": None, "stat": 0},
        ),
        outcome_weights=(("离院回家", 86), ("住院", 10), ("转院", 4), ("死亡", 0)),
        past_histories=("哮喘病史", "无特殊既往史"),
        allergies=("头孢过敏", "无特殊过敏史"),
    ),
    Scenario(
        key="gastroenteritis",
        diagnosis="急性胃肠炎",
        icd="A09",
        complaints=("恶心呕吐腹泻1天", "腹泻伴腹痛半天", "进食不洁后呕吐4次"),
        histories=(
            "进食外卖后出现恶心呕吐及腹泻，伴轻度腹痛，无明显发热。",
            "多次稀水样便，伴乏力口干，入院前未补液。",
        ),
        triage_levels=(3, 4, 4),
        arrival_modes=("步行",),
        green_type=None,
        green_prob=0.0,
        rescue_prob=0.0,
        observation_prob=0.12,
        trauma=False,
        pediatric=False,
        lab_names=("血常规", "电解质", "急诊生化"),
        imaging_names=(),
        order_templates=(
            {"type": "药品", "category": "临时", "content": "昂丹司琼 4mg 静推", "dosage": "4mg", "frequency": "STAT", "route": "静脉注射", "stat": 0},
            {"type": "药品", "category": "长期", "content": "乳酸林格液 500ml 静滴", "dosage": "500ml", "frequency": "QD", "route": "静脉滴注", "stat": 0},
        ),
        outcome_weights=(("离院回家", 82), ("住院", 12), ("转院", 5), ("死亡", 1)),
        past_histories=("无特殊既往史", "慢性胃炎"),
        allergies=("无特殊过敏史", "布洛芬胃溃疡风险"),
    ),
    Scenario(
        key="fracture",
        diagnosis="四肢骨折待排",
        icd="S82.9",
        complaints=("摔伤后踝部肿痛2小时", "手腕外伤后疼痛1小时", "运动损伤后不能负重"),
        histories=(
            "运动时不慎扭伤，局部肿胀疼痛，活动受限。",
            "跌倒后上肢着地，腕部疼痛明显，不能持物。",
        ),
        triage_levels=(3, 4, 4),
        arrival_modes=("步行", "轮椅"),
        green_type=None,
        green_prob=0.0,
        rescue_prob=0.01,
        observation_prob=0.08,
        trauma=True,
        pediatric=False,
        lab_names=("血常规",),
        imaging_names=("四肢X线",),
        order_templates=(
            {"type": "药品", "category": "临时", "content": "布洛芬缓释胶囊 0.3g 口服", "dosage": "0.3g", "frequency": "STAT", "route": "口服", "stat": 0},
            {"type": "检查", "category": "临时", "content": "四肢X线", "dosage": None, "frequency": "STAT", "route": None, "stat": 0},
        ),
        outcome_weights=(("离院回家", 68), ("住院", 18), ("转院", 12), ("死亡", 2)),
        past_histories=("无特殊既往史",),
        allergies=("无特殊过敏史",),
    ),
]


def choose_weighted(rng: random.Random, weighted):
    labels = [item[0] for item in weighted]
    weights = [item[1] for item in weighted]
    return rng.choices(labels, weights=weights, k=1)[0]


def chinese_name(rng: random.Random) -> str:
    surname = rng.choice(SURNAME_POOL)
    given = rng.choice(NAME_POOL) + rng.choice(NAME_POOL)
    return surname + given


def random_phone(seq: int) -> str:
    return f"139{seq:08d}"[-11:]


def random_id_card(seq: int, birth_day: date, gender: str) -> str:
    region = "110101"
    base = birth_day.strftime("%Y%m%d")
    order = f"{seq % 1000:03d}"
    if gender == "M":
        if int(order[-1]) % 2 == 0:
            order = order[:-1] + "1"
    else:
        if int(order[-1]) % 2 == 1:
            order = order[:-1] + "2"
    checksum = str((seq * 7) % 10)
    return f"{region}{base}{order}{checksum}"


def exam_result_for(scenario: Scenario, exam_name: str, rng: random.Random, level: int):
    if exam_name == "肌钙蛋白I":
        value = round(rng.uniform(0.08, 4.2) if scenario.key == "chest_pain" else rng.uniform(0.01, 0.06), 3)
        flag = "HH" if value >= 1.5 else "H" if value > 0.04 else "N"
        return value, "ng/ml", flag, "0-0.04", None
    if exam_name == "CK-MB":
        value = round(rng.uniform(18, 90) if scenario.key == "chest_pain" else rng.uniform(10, 28), 1)
        flag = "H" if value > 25 else "N"
        return value, "U/L", flag, "0-25", None
    if exam_name == "血糖":
        value = round(rng.uniform(4.2, 12.0), 1)
        flag = "H" if value > 6.1 else "N"
        return value, "mmol/L", flag, "3.9-6.1", None
    if exam_name == "血气分析":
        value = round(rng.uniform(58, 82) if scenario.key == "dyspnea" else rng.uniform(80, 98), 1)
        flag = "LL" if value < 60 else "L" if value < 75 else "N"
        return value, "mmHg", flag, "80-100", None
    if exam_name == "C反应蛋白":
        value = round(rng.uniform(8, 68) if scenario.key in ("fever", "dyspnea", "abdomen") else rng.uniform(1, 12), 1)
        flag = "H" if value > 10 else "N"
        return value, "mg/L", flag, "0-10", None
    if exam_name == "降钙素原":
        value = round(rng.uniform(0.05, 4.5), 2)
        flag = "H" if value > 0.5 else "N"
        return value, "ng/ml", flag, "0-0.5", None
    if exam_name == "淀粉酶":
        value = round(rng.uniform(45, 420) if scenario.key == "abdomen" else rng.uniform(40, 120), 1)
        flag = "H" if value > 125 else "N"
        return value, "U/L", flag, "25-125", None
    if exam_name == "BNP/NT-proBNP":
        value = round(rng.uniform(180, 1800) if scenario.key == "dyspnea" else rng.uniform(50, 260), 0)
        flag = "H" if value > 300 else "N"
        return value, "pg/ml", flag, "0-300", None
    if exam_name == "电解质":
        value = round(rng.uniform(132, 145), 1)
        flag = "L" if value < 135 else "N"
        return value, "mmol/L", flag, "135-145", None
    if exam_name in ("血常规", "急诊生化", "凝血四项", "血型鉴定", "交叉配血"):
        return None, None, None, None, "已完成"
    return None, None, None, None, None


def imaging_report_for(scenario: Scenario, exam_name: str):
    if exam_name == "头颅CT平扫":
        return "左侧基底节区低密度影，脑沟变浅。", "考虑急性脑梗死，建议结合CTA进一步评估。"
    if exam_name == "头颅CTA":
        return "左侧大脑中动脉M1段局部狭窄。", "考虑大血管闭塞倾向，建议卒中团队进一步处理。"
    if exam_name == "胸部CT平扫":
        if scenario.key == "chest_pain":
            return "主动脉壁钙化，双肺纹理增粗。", "未见明显主动脉夹层征象。"
        return "双肺纹理增粗，局部片状密度增高影。", "考虑感染或慢阻肺急性加重。"
    if exam_name == "腹部CT平扫":
        return "阑尾轻度增粗，周围脂肪间隙模糊。", "考虑急性阑尾炎可能。"
    if exam_name == "四肢X线":
        return "局部软组织肿胀，骨皮质连续性欠佳。", "考虑可疑骨折，建议骨科会诊。"
    if exam_name == "胸部X线":
        return "双肺纹理增多，心影稍大。", "结合临床考虑感染或心衰。"
    if exam_name == "急诊超声":
        return "胆囊壁轻度毛糙，腹腔未见明显积液。", "建议结合实验室结果综合判断。"
    return "未见明显急性异常影像学改变。", "建议结合临床。"


def triage_vitals(scenario: Scenario, level: int, rng: random.Random):
    hr = rng.randint(65, 100)
    sbp = rng.randint(108, 148)
    dbp = rng.randint(65, 92)
    temp = round(rng.uniform(36.4, 37.4), 1)
    rr = rng.randint(16, 22)
    spo2 = rng.randint(96, 100)
    pain = rng.randint(1, 5)
    consciousness = "清醒"

    if scenario.key == "chest_pain":
        hr = rng.randint(84, 122)
        sbp = rng.randint(105, 168)
        pain = rng.randint(6, 9)
        spo2 = rng.randint(92, 98)
    elif scenario.key == "stroke":
        hr = rng.randint(72, 110)
        sbp = rng.randint(150, 210)
        dbp = rng.randint(88, 116)
        pain = rng.randint(0, 3)
        consciousness = "嗜睡" if level == 1 and rng.random() < 0.45 else "清醒"
    elif scenario.key == "trauma":
        hr = rng.randint(90, 135)
        sbp = rng.randint(86, 138)
        dbp = rng.randint(55, 88)
        pain = rng.randint(6, 10)
        spo2 = rng.randint(90, 98)
    elif scenario.key == "abdomen":
        hr = rng.randint(72, 108)
        temp = round(rng.uniform(36.7, 38.5), 1)
        pain = rng.randint(4, 8)
    elif scenario.key == "dyspnea":
        hr = rng.randint(88, 125)
        rr = rng.randint(24, 36)
        spo2 = rng.randint(84, 95)
        temp = round(rng.uniform(36.8, 38.6), 1)
        pain = rng.randint(1, 4)
    elif scenario.key == "fever":
        temp = round(rng.uniform(38.1, 39.8), 1)
        hr = rng.randint(86, 118)
        rr = rng.randint(18, 28)
    elif scenario.key == "pediatric_fever":
        temp = round(rng.uniform(38.0, 39.7), 1)
        hr = rng.randint(102, 142)
        rr = rng.randint(22, 32)
        sbp = None
        dbp = None
    elif scenario.key == "gastroenteritis":
        hr = rng.randint(74, 108)
        temp = round(rng.uniform(36.7, 38.2), 1)
        pain = rng.randint(2, 5)
    elif scenario.key == "fracture":
        pain = rng.randint(5, 8)
        hr = rng.randint(72, 98)

    if level == 1:
        hr = max(hr, rng.randint(105, 135))
        rr = max(rr, rng.randint(24, 38))
        spo2 = min(spo2, rng.randint(82, 93))
        pain = max(pain, rng.randint(7, 10))
    elif level == 2:
        pain = max(pain, rng.randint(5, 8))
        spo2 = min(spo2, rng.randint(88, 96))

    return {
        "hr": hr,
        "bp_s": sbp,
        "bp_d": dbp,
        "temperature": temp,
        "rr": rr,
        "spo2": spo2,
        "pain": pain,
        "consciousness": consciousness,
    }


def build_visit_time(rng: random.Random, now: datetime) -> datetime:
    bucket = rng.choices(
        ["current_shift", "today_earlier", "overnight", "recent_history", "older_history"],
        weights=[38, 26, 14, 14, 8],
        k=1,
    )[0]
    if bucket == "current_shift":
        return now - timedelta(minutes=rng.randint(8, 360))
    if bucket == "today_earlier":
        base = datetime.combine(now.date(), time(rng.randint(0, max(0, now.hour - 1)), rng.randint(0, 59)))
        return base
    if bucket == "overnight":
        visit_day = now.date() - timedelta(days=1)
        return datetime.combine(visit_day, time(rng.randint(18, 23), rng.randint(0, 59)))
    if bucket == "recent_history":
        visit_day = now.date() - timedelta(days=rng.randint(1, 3))
        return datetime.combine(visit_day, time(rng.randint(7, 22), rng.randint(0, 59)))
    visit_day = now.date() - timedelta(days=rng.randint(4, 6))
    return datetime.combine(visit_day, time(rng.randint(7, 22), rng.randint(0, 59)))


def shift_timestamp_columns(cur, table: str, columns: list[str], where_sql: str, params: tuple, delta_minutes: int):
    if not delta_minutes:
        return
    set_sql = ", ".join(
        f"{column}=CASE WHEN {column} IS NULL THEN NULL ELSE TIMESTAMPADD(MINUTE, %s, {column}) END"
        for column in columns
    )
    cur.execute(
        f"UPDATE {table} SET {set_sql} WHERE {where_sql}",
        tuple([delta_minutes] * len(columns)) + params,
    )


def refresh_operational_snapshot(cur, rng: random.Random, now: datetime):
    cur.execute(
        """
        SELECT visit_id, visit_status, visit_time, triage_level, triage_time
        FROM ed_visit
        WHERE visit_status IN ('分诊中', '候诊', '就诊中', '观察中', '处置中', '待入院')
        ORDER BY visit_time DESC
        """
    )
    active_rows = cur.fetchall()
    for row in active_rows:
        level = row["triage_level"] or 4
        if row["visit_status"] == "分诊中":
            minutes_back = rng.randint(4, 28)
        elif row["visit_status"] == "候诊":
            ranges = {1: (6, 24), 2: (10, 36), 3: (18, 75), 4: (35, 150), 5: (60, 210)}
            minutes_back = rng.randint(*ranges.get(level, (20, 90)))
        elif row["visit_status"] == "处置中":
            ranges = {1: (35, 160), 2: (45, 220), 3: (70, 320), 4: (90, 420), 5: (120, 480)}
            minutes_back = rng.randint(*ranges.get(level, (60, 260)))
        elif row["visit_status"] == "就诊中":
            ranges = {1: (55, 220), 2: (70, 320), 3: (95, 420), 4: (130, 540), 5: (160, 620)}
            minutes_back = rng.randint(*ranges.get(level, (90, 360)))
        elif row["visit_status"] == "观察中":
            minutes_back = rng.randint(240, 960)
        else:
            minutes_back = rng.randint(320, 1080)

        new_visit_time = now - timedelta(minutes=minutes_back)
        delta_minutes = int((new_visit_time - row["visit_time"]).total_seconds() // 60)
        if not delta_minutes:
            continue

        shift_timestamp_columns(cur, "ed_triage_assessment", ["assess_time"], "visit_id=%s", (row["visit_id"],), delta_minutes)
        shift_timestamp_columns(cur, "ed_medical_record", ["record_time"], "visit_id=%s", (row["visit_id"],), delta_minutes)
        shift_timestamp_columns(cur, "ed_order", ["order_time", "review_time", "stop_time"], "visit_id=%s", (row["visit_id"],), delta_minutes)
        shift_timestamp_columns(cur, "ed_order_execution", ["execute_time"], "order_id IN (SELECT order_id FROM ed_order WHERE visit_id=%s)", (row["visit_id"],), delta_minutes)
        shift_timestamp_columns(cur, "ed_lab_order", ["order_time", "specimen_time", "receive_time", "report_time", "confirm_time"], "visit_id=%s", (row["visit_id"],), delta_minutes)
        shift_timestamp_columns(cur, "ed_imaging_order", ["order_time", "arrive_time", "exam_time", "report_time", "confirm_time"], "visit_id=%s", (row["visit_id"],), delta_minutes)
        shift_timestamp_columns(cur, "ed_nursing_record", ["record_time"], "visit_id=%s", (row["visit_id"],), delta_minutes)
        shift_timestamp_columns(cur, "ed_observation", ["obs_start", "obs_end", "latest_reassess_time"], "visit_id=%s", (row["visit_id"],), delta_minutes)
        shift_timestamp_columns(cur, "ed_consultation", ["request_time", "response_time", "completed_time"], "visit_id=%s", (row["visit_id"],), delta_minutes)
        shift_timestamp_columns(cur, "ed_green_channel", ["activate_time", "latest_event_time", "completed_time"], "visit_id=%s", (row["visit_id"],), delta_minutes)
        shift_timestamp_columns(cur, "ed_green_channel_event", ["event_time"], "visit_id=%s", (row["visit_id"],), delta_minutes)
        shift_timestamp_columns(cur, "ed_rescue_record", ["rescue_start", "rescue_end", "latest_event_time", "cpr_start", "rosc_time"], "visit_id=%s", (row["visit_id"],), delta_minutes)
        shift_timestamp_columns(cur, "ed_rescue_timeline", ["event_time"], "visit_id=%s", (row["visit_id"],), delta_minutes)
        shift_timestamp_columns(cur, "ed_critical_value", ["notify_time", "acknowledged_at"], "visit_id=%s", (row["visit_id"],), delta_minutes)

        triage_offset = rng.randint(2, 10)
        cur.execute(
            """
            UPDATE ed_visit
            SET visit_time=%s,
                visit_date=%s,
                triage_time=%s,
                outcome_time=NULL
            WHERE visit_id=%s
            """,
            (new_visit_time, new_visit_time.date(), new_visit_time + timedelta(minutes=triage_offset), row["visit_id"]),
        )


def bed_rebuild(cur):
    cur.execute(
        """
        SELECT visit_id, triage_level, visit_status, is_120_transfer
        FROM ed_visit
        WHERE visit_status IN ('候诊', '就诊中', '观察中', '处置中', '待入院')
        ORDER BY
            CASE visit_status
                WHEN '处置中' THEN 1
                WHEN '就诊中' THEN 2
                WHEN '观察中' THEN 3
                WHEN '待入院' THEN 4
                WHEN '候诊' THEN 5
                ELSE 6
            END,
            CASE WHEN triage_level IS NULL THEN 9 ELSE triage_level END ASC,
            is_120_transfer DESC,
            visit_time ASC
        """
    )
    active_visits = cur.fetchall()
    cur.execute("SELECT bed_id, bed_code FROM ed_bed WHERE bed_code <> 'R-05' ORDER BY bed_id")
    beds = cur.fetchall()
    cleanup_beds = {12}

    cur.execute("UPDATE ed_visit SET bed_id=NULL WHERE visit_status IN ('候诊', '就诊中', '观察中', '处置中')")
    cur.execute("UPDATE ed_bed SET bed_status='空闲', current_visit_id=NULL WHERE bed_code <> 'R-05'")
    cur.execute("UPDATE ed_bed SET bed_status='维修', current_visit_id=NULL WHERE bed_code='R-05'")
    if cleanup_beds:
        cur.execute(
            f"UPDATE ed_bed SET bed_status='清洁中', current_visit_id=NULL WHERE bed_id IN ({','.join(['%s'] * len(cleanup_beds))})",
            tuple(cleanup_beds),
        )

    assignable_beds = [b["bed_id"] for b in beds if b["bed_id"] not in cleanup_beds]
    occupied_pool = [v for v in active_visits if v["visit_status"] in ("处置中", "就诊中", "观察中", "待入院")]
    waiting_critical = [v for v in active_visits if v["visit_status"] == "候诊" and (v["triage_level"] or 9) <= 2]
    occupied_visits = (occupied_pool + waiting_critical)[: min(len(active_visits), min(20, len(assignable_beds)))]
    for idx, visit in enumerate(occupied_visits):
        bed_id = assignable_beds[idx]
        cur.execute("UPDATE ed_visit SET bed_id=%s WHERE visit_id=%s", (bed_id, visit["visit_id"]))
        cur.execute("UPDATE ed_bed SET bed_status='占用', current_visit_id=%s WHERE bed_id=%s", (visit["visit_id"], bed_id))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-patients", type=int, default=200)
    parser.add_argument("--target-visits", type=int, default=240)
    parser.add_argument("--seed", type=int, default=20260424)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    now = datetime.now()

    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS c FROM patient_info")
            patient_count = cur.fetchone()["c"]
            cur.execute("SELECT COUNT(*) AS c FROM ed_visit")
            visit_count = cur.fetchone()["c"]
            cur.execute("SELECT COUNT(*) AS c FROM patient_info WHERE patient_no REGEXP '^P[0-9]+'")
            _ = cur.fetchone()["c"]
            cur.execute("SELECT IFNULL(MAX(CAST(RIGHT(patient_no, 4) AS UNSIGNED)), 0) AS seq FROM patient_info")
            patient_seq = int(cur.fetchone()["seq"] or 0)
            cur.execute("SELECT visit_date, IFNULL(MAX(CAST(RIGHT(visit_no, 3) AS UNSIGNED)), 0) AS seq FROM ed_visit GROUP BY visit_date")
            visit_seq = {row["visit_date"]: int(row["seq"] or 0) for row in cur.fetchall()}
            cur.execute("SELECT staff_id, role_type FROM sys_staff WHERE is_active=1")
            staff_rows = cur.fetchall()
            doctor_ids = [r["staff_id"] for r in staff_rows if r["role_type"] == "医生"] or [1]
            nurse_ids = [r["staff_id"] for r in staff_rows if r["role_type"] == "护士"] or [7]
            triage_ids = [r["staff_id"] for r in staff_rows if r["role_type"] == "分诊员"] or [12]
            lab_staff_id = next((r["staff_id"] for r in staff_rows if r["role_type"] == "检验"), 18)
            imaging_staff_id = next((r["staff_id"] for r in staff_rows if r["role_type"] == "影像"), 19)

            cur.execute("SELECT exam_id, exam_name FROM sys_exam_dict")
            exam_map = {row["exam_name"]: row["exam_id"] for row in cur.fetchall()}

            cur.execute("SELECT patient_id FROM patient_info ORDER BY patient_id")
            existing_patient_ids = [row["patient_id"] for row in cur.fetchall()]

            patients_to_add = max(0, args.target_patients - patient_count)
            visits_to_add = max(0, args.target_visits - visit_count)

            new_patient_ids = []
            for _ in range(patients_to_add):
                patient_seq += 1
                scenario = rng.choice(SCENARIOS)
                gender = rng.choice(["M", "F"])
                age = rng.randint(2, 12) if scenario.pediatric else rng.randint(18, 86)
                age_unit = "岁"
                birth_day = now.date() - timedelta(days=365 * age + rng.randint(0, 360))
                patient_no = f"P2026{patient_seq:04d}"
                name = chinese_name(rng)
                phone = random_phone(20000000 + patient_seq)
                patient_id_card = random_id_card(8000 + patient_seq, birth_day, gender)
                cur.execute(
                    """
                    INSERT INTO patient_info (
                        patient_no, id_card_no, patient_name, gender, birth_date, age, age_unit, phone,
                        address, emergency_contact, emergency_phone, blood_type, allergy_history, past_history, insurance_type
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        patient_no,
                        patient_id_card,
                        name,
                        gender,
                        birth_day,
                        age,
                        age_unit,
                        phone,
                        "北京市朝阳区急诊演示街道" + str(patient_seq % 88 + 1) + "号",
                        chinese_name(rng),
                        random_phone(30000000 + patient_seq),
                        rng.choice(["A", "B", "O", "AB"]),
                        rng.choice(scenario.allergies),
                        rng.choice(scenario.past_histories),
                        rng.choice(["城镇职工", "城乡居民", "自费"]),
                    ),
                )
                new_patient_ids.append(cur.lastrowid)

            all_patient_ids = existing_patient_ids + new_patient_ids
            if visits_to_add < len(new_patient_ids):
                visits_to_add = len(new_patient_ids)

            patient_queue = list(new_patient_ids)
            while len(patient_queue) < visits_to_add:
                patient_queue.append(rng.choice(all_patient_ids))
            rng.shuffle(patient_queue)

            created_visit_ids = []

            for idx in range(visits_to_add):
                patient_id = patient_queue[idx]
                scenario = rng.choices(
                    SCENARIOS,
                    weights=[12, 8, 10, 15, 12, 15, 10, 8, 10],
                    k=1,
                )[0]
                visit_time = build_visit_time(rng, now)
                visit_date = visit_time.date()
                visit_seq[visit_date] = visit_seq.get(visit_date, 0) + 1
                visit_no = f"ED{visit_date:%Y%m%d}{visit_seq[visit_date]:03d}"
                triage_level = rng.choice(scenario.triage_levels)
                vitals = triage_vitals(scenario, triage_level, rng)
                arrival_mode = rng.choice(scenario.arrival_modes)
                doctor_id = rng.choice(doctor_ids)
                triage_id = rng.choice(triage_ids)
                chief_complaint = rng.choice(scenario.complaints)
                present_illness = rng.choice(scenario.histories)

                is_recent = visit_date >= now.date() - timedelta(days=1)
                is_active = is_recent and rng.random() < (0.52 if triage_level <= 2 else 0.28)
                if is_active:
                    visit_status = choose_weighted(
                        rng,
                        (("候诊", 12), ("就诊中", 38), ("观察中", 24), ("处置中", 26)),
                    )
                    outcome = None
                    outcome_time = None
                else:
                    visit_status = "已离院"
                    outcome = choose_weighted(rng, scenario.outcome_weights)
                    if outcome == "住院":
                        visit_status = "待入院"
                    elif outcome == "转院":
                        visit_status = "已转院"
                    elif outcome == "死亡":
                        visit_status = "死亡"
                    outcome_time = visit_time + timedelta(minutes=rng.randint(45, 420))

                is_green = 1 if scenario.green_type and triage_level <= 2 and rng.random() < scenario.green_prob else 0
                cur.execute(
                    """
                    INSERT INTO ed_visit (
                        visit_no, patient_id, visit_date, visit_time, arrival_mode, chief_complaint,
                        present_illness, triage_level, triage_color, triage_time, triage_nurse_id,
                        triage_vitals, attending_doctor_id, bed_id, visit_status, outcome, outcome_time,
                        icd_code, is_green_channel, is_trauma, is_pediatric, is_120_transfer, priority_score, triage_reason
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        visit_no,
                        patient_id,
                        visit_date,
                        visit_time,
                        arrival_mode,
                        chief_complaint,
                        present_illness,
                        triage_level,
                        TRIAGE_COLORS[triage_level],
                        visit_time + timedelta(minutes=2),
                        triage_id,
                        json.dumps(
                            {
                                "HR": vitals["hr"],
                                "BP_S": vitals["bp_s"],
                                "BP_D": vitals["bp_d"],
                                "Temp": vitals["temperature"],
                                "RR": vitals["rr"],
                                "SpO2": vitals["spo2"],
                                "Pain": vitals["pain"],
                            },
                            ensure_ascii=False,
                        ),
                        doctor_id,
                        visit_status,
                        outcome,
                        outcome_time,
                        scenario.icd,
                        is_green,
                        1 if scenario.trauma else 0,
                        1 if scenario.pediatric else 0,
                        1 if arrival_mode == "120急救" else 0,
                        max(20, 120 - triage_level * 18 + rng.randint(-10, 12)),
                        f"{scenario.diagnosis}场景自动生成",
                    ),
                )
                visit_id = cur.lastrowid
                created_visit_ids.append(visit_id)

                cur.execute(
                    """
                    INSERT INTO ed_triage_assessment (
                        visit_id, assess_time, nurse_id, consciousness, pain_score, hr, bp_systolic,
                        bp_diastolic, temperature, rr, spo2, weight, fall_risk, skin_integrity,
                        triage_level, triage_category, chief_complaint, brief_history, allergy_flag, pregnancy_flag
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        visit_id,
                        visit_time + timedelta(minutes=2),
                        triage_id,
                        vitals["consciousness"],
                        vitals["pain"],
                        vitals["hr"],
                        vitals["bp_s"],
                        vitals["bp_d"],
                        vitals["temperature"],
                        vitals["rr"],
                        vitals["spo2"],
                        round(rng.uniform(25, 85), 1),
                        rng.choice(["低", "中", "高"]),
                        "完整" if not scenario.trauma or rng.random() < 0.5 else "破损",
                        triage_level,
                        scenario.diagnosis,
                        chief_complaint,
                        present_illness,
                        1 if rng.random() < 0.12 else 0,
                        1 if rng.random() < 0.03 else 0,
                    ),
                )

                if rng.random() < 0.78:
                    cur.execute(
                        """
                        INSERT INTO ed_medical_record (
                            visit_id, doctor_id, record_time, record_type, chief_complaint, present_illness,
                            physical_exam, assessment, treatment_plan, doctor_orders, hr, bp_systolic,
                            bp_diastolic, temperature, rr, spo2
                        ) VALUES (%s, %s, %s, '初诊', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            visit_id,
                            doctor_id,
                            visit_time + timedelta(minutes=12),
                            chief_complaint,
                            present_illness,
                            "神志" + vitals["consciousness"] + "，呼吸音粗，生命体征见急诊分诊。",
                            scenario.diagnosis,
                            "完善急诊评估，按病种路径处置。",
                            "已下达相关检验、影像及护理医嘱。",
                            vitals["hr"],
                            vitals["bp_s"],
                            vitals["bp_d"],
                            vitals["temperature"],
                            vitals["rr"],
                            vitals["spo2"],
                        ),
                    )

                cur.execute(
                    """
                    INSERT INTO ed_diagnosis (
                        visit_id, icd_code, diagnosis_name, diagnosis_type, doctor_id, diagnose_time, is_primary
                    ) VALUES (%s, %s, %s, '初步诊断', %s, %s, 1)
                    """,
                    (visit_id, scenario.icd, scenario.diagnosis, doctor_id, visit_time + timedelta(minutes=15)),
                )

                completed_med_orders = []
                for template in scenario.order_templates:
                    order_time = visit_time + timedelta(minutes=rng.randint(5, 25))
                    if is_active:
                        order_status = choose_weighted(rng, (("待执行", 25), ("执行中", 35), ("已完成", 40)))
                    else:
                        order_status = choose_weighted(rng, (("已完成", 82), ("执行中", 10), ("待执行", 8)))
                    cur.execute(
                        """
                        INSERT INTO ed_order (
                            visit_id, order_time, doctor_id, order_type, order_category, order_content,
                            dosage, frequency, route, is_stat, order_status, review_status, reviewer_id, review_time
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, '已审核', %s, %s)
                        """,
                        (
                            visit_id,
                            order_time,
                            doctor_id,
                            template["type"],
                            template["category"],
                            template["content"],
                            template["dosage"],
                            template["frequency"],
                            template["route"],
                            template["stat"],
                            order_status,
                            doctor_id,
                            order_time,
                        ),
                    )
                    order_id = cur.lastrowid
                    if template["type"] == "药品" and order_status == "已完成":
                        completed_med_orders.append((order_id, order_time))

                extra_order_count = rng.randint(0, 2)
                for extra_idx in range(extra_order_count):
                    order_time = visit_time + timedelta(minutes=rng.randint(10, 40))
                    content = rng.choice([
                        "心电监护",
                        "吸氧 3L/min",
                        "建立静脉通路",
                        "复查血糖",
                        "复测生命体征",
                    ])
                    order_type = "护理" if "生命体征" in content or "静脉" in content else "治疗"
                    order_status = choose_weighted(rng, (("待执行", 22), ("执行中", 18), ("已完成", 60)))
                    cur.execute(
                        """
                        INSERT INTO ed_order (
                            visit_id, order_time, doctor_id, order_type, order_category, order_content,
                            dosage, frequency, route, is_stat, order_status, review_status, reviewer_id, review_time
                        ) VALUES (%s, %s, %s, %s, '临时', %s, NULL, 'STAT', NULL, 0, %s, '已审核', %s, %s)
                        """,
                        (visit_id, order_time, doctor_id, order_type, content, order_status, doctor_id, order_time),
                    )

                for order_id, order_time in completed_med_orders[:2]:
                    execute_time = order_time + timedelta(minutes=rng.randint(8, 35))
                    cur.execute(
                        """
                        INSERT INTO ed_order_execution (
                            order_id, execute_time, execute_nurse_id, execution_status, result_note, vital_snapshot
                        ) VALUES (%s, %s, %s, '已执行', %s, %s)
                        """,
                        (
                            order_id,
                            execute_time,
                            rng.choice(nurse_ids),
                            "按医嘱执行",
                            json.dumps({"HR": vitals["hr"], "SpO2": vitals["spo2"]}, ensure_ascii=False),
                        ),
                    )

                for lab_name in scenario.lab_names:
                    if lab_name not in exam_map:
                        continue
                    order_time = visit_time + timedelta(minutes=rng.randint(5, 30))
                    specimen_time = order_time + timedelta(minutes=rng.randint(3, 18))
                    reported = (not is_active) or rng.random() < 0.62
                    receive_time = specimen_time + timedelta(minutes=rng.randint(3, 15))
                    report_time = receive_time + timedelta(minutes=rng.randint(18, 55)) if reported else None
                    result_value, result_unit, result_flag, ref_range, result_text = exam_result_for(scenario, lab_name, rng, triage_level)
                    lab_status = "已报告" if reported else choose_weighted(rng, (("待采集", 15), ("已采集", 20), ("检验中", 65)))
                    cur.execute(
                        """
                        INSERT INTO ed_lab_order (
                            visit_id, exam_id, order_time, doctor_id, specimen_type, specimen_time,
                            collect_nurse_id, receive_time, lab_technician_id, confirm_doctor_id, confirm_time,
                            is_stat, lab_status, report_time, result_value, result_unit, result_flag, result_text, reference_range
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            visit_id,
                            exam_map[lab_name],
                            order_time,
                            doctor_id,
                            "全血" if lab_name == "血常规" else "血清",
                            specimen_time if lab_status != "待采集" else None,
                            rng.choice(nurse_ids) if lab_status != "待采集" else None,
                            receive_time if lab_status in ("检验中", "已报告") else None,
                            lab_staff_id if lab_status in ("检验中", "已报告") else None,
                            doctor_id if reported and rng.random() < 0.55 else None,
                            report_time + timedelta(minutes=rng.randint(3, 22)) if reported and rng.random() < 0.55 else None,
                            1 if triage_level <= 2 else 0,
                            lab_status,
                            report_time,
                            result_value,
                            result_unit,
                            result_flag,
                            result_text,
                            ref_range,
                        ),
                    )
                    lab_id = cur.lastrowid
                    if result_flag in ("HH", "LL"):
                        acked = rng.random() < 0.55
                        notify_time = report_time or (receive_time + timedelta(minutes=20))
                        cur.execute(
                            """
                            INSERT IGNORE INTO ed_critical_value (
                                lab_id, visit_id, critical_level, item_name, result_value, reference_range,
                                notify_doctor_id, notify_time, acknowledged_by, acknowledged_at, action_note, status
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            """,
                            (
                                lab_id,
                                visit_id,
                                result_flag,
                                lab_name,
                                str(result_value) if result_value is not None else result_text,
                                ref_range,
                                doctor_id,
                                notify_time,
                                doctor_id if acked else None,
                                notify_time + timedelta(minutes=rng.randint(4, 28)) if acked else None,
                                "已电话通知值班医生" if acked else None,
                                "已处理" if acked else "未确认",
                            ),
                        )

                for imaging_name in scenario.imaging_names:
                    if imaging_name not in exam_map:
                        continue
                    order_time = visit_time + timedelta(minutes=rng.randint(8, 35))
                    started = (not is_active) or rng.random() < 0.78
                    reported = started and ((not is_active) or rng.random() < 0.68)
                    exam_time = order_time + timedelta(minutes=rng.randint(12, 55)) if started else None
                    report_time = exam_time + timedelta(minutes=rng.randint(18, 70)) if reported else None
                    report_text, impression = imaging_report_for(scenario, imaging_name)
                    imaging_status = "已报告" if reported else ("检查中" if started else "待检查")
                    cur.execute(
                        """
                        INSERT INTO ed_imaging_order (
                            visit_id, exam_id, order_time, doctor_id, arrive_time, technician_id,
                            is_stat, imaging_status, exam_time, report_time, report_text, impression,
                            radiologist_id, confirm_doctor_id, confirm_time, exam_room
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            visit_id,
                            exam_map[imaging_name],
                            order_time,
                            doctor_id,
                            order_time + timedelta(minutes=5) if started else None,
                            imaging_staff_id if started else None,
                            1 if triage_level <= 2 else 0,
                            imaging_status,
                            exam_time,
                            report_time,
                            report_text if reported else None,
                            impression if reported else None,
                            imaging_staff_id if reported else None,
                            doctor_id if reported and rng.random() < 0.5 else None,
                            report_time + timedelta(minutes=rng.randint(4, 18)) if reported and rng.random() < 0.5 else None,
                            rng.choice(["CT-1", "CT-2", "DR-1", "超声-1"]),
                        ),
                    )

                nursing_count = rng.randint(1, 4 if is_active else 3)
                for n_idx in range(nursing_count):
                    record_time = visit_time + timedelta(minutes=15 + n_idx * rng.randint(20, 60))
                    cur.execute(
                        """
                        INSERT INTO ed_nursing_record (
                            visit_id, nurse_id, record_time, record_type, hr, bp_systolic, bp_diastolic,
                            temperature, rr, spo2, consciousness, pain_score, intake_ml, output_ml,
                            iv_fluid, nursing_content, special_notes
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            visit_id,
                            rng.choice(nurse_ids),
                            record_time,
                            "抢救" if triage_level == 1 and n_idx == 0 else "常规",
                            max(55, vitals["hr"] + rng.randint(-12, 8)),
                            vitals["bp_s"],
                            vitals["bp_d"],
                            round(max(35.5, vitals["temperature"] + rng.uniform(-0.3, 0.3)), 1),
                            max(12, vitals["rr"] + rng.randint(-3, 3)),
                            max(80, min(100, vitals["spo2"] + rng.randint(-2, 3))),
                            vitals["consciousness"],
                            max(0, vitals["pain"] - rng.randint(0, 2)),
                            rng.randint(0, 600),
                            rng.randint(0, 400),
                            rng.choice(["0.9%NS 250ml", "乳酸林格液 500ml", "葡萄糖注射液 250ml", None]),
                            rng.choice(["持续监测生命体征", "遵医嘱给药并评估反应", "保持气道通畅", "观察疼痛变化与意识状态"]),
                            rng.choice(["无特殊", "患者家属已宣教", "继续严密观察", "待复查结果回报"]),
                        ),
                    )

                if rng.random() < scenario.observation_prob:
                    obs_start = visit_time + timedelta(minutes=rng.randint(40, 150))
                    obs_active = is_active and visit_status == "观察中"
                    obs_end = None if obs_active else obs_start + timedelta(hours=rng.randint(4, 22))
                    obs_outcome = None if obs_active else choose_weighted(rng, (("离院", 46), ("住院", 38), ("转院", 16)))
                    obs_status = "观察中" if obs_active else ("待入院" if obs_outcome == "住院" else "已完成")
                    cur.execute(
                        """
                        INSERT INTO ed_observation (
                            visit_id, bed_id, responsible_doctor_id, obs_start, obs_end, obs_duration,
                            obs_reason, reassess_count, latest_reassess_time, outcome, dest_dept, dest_ward, obs_status
                        ) VALUES (%s, NULL, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            visit_id,
                            doctor_id,
                            obs_start,
                            obs_end,
                            int((obs_end - obs_start).total_seconds() // 3600) if obs_end else None,
                            rng.choice(["待复评症状", "待复查检验结果", "待影像结果回报", "短期动态观察"]),
                            rng.randint(0, 3),
                            (obs_start + timedelta(hours=2)) if obs_active else obs_end,
                            obs_outcome,
                            rng.choice(["心内科", "神经内科", "普外科", "呼吸科"]) if obs_outcome == "住院" else None,
                            rng.choice(["病区A", "病区B", "ICU"]) if obs_outcome == "住院" else None,
                            obs_status,
                        ),
                    )

                if triage_level <= 2 and rng.random() < 0.09:
                    cur.execute(
                        """
                        INSERT INTO ed_consultation (
                            visit_id, request_time, request_doctor_id, requested_dept_id, requested_staff_id,
                            consult_reason, urgency_level, consult_status, response_time, responder_id, consult_opinion,
                            advice_plan, completed_time
                        ) VALUES (%s, %s, %s, %s, NULL, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            visit_id,
                            visit_time + timedelta(minutes=35),
                            doctor_id,
                            rng.choice([1, 2, 3, 4, 5, 6]),
                            rng.choice(["请心内科评估介入时机", "请神经内科评估溶栓指征", "请外科评估急腹症可能", "请ICU评估收治"]),
                            rng.choice(["普通", "加急", "紧急"]),
                            rng.choice(["待响应", "进行中", "已完成"]),
                            visit_time + timedelta(minutes=50),
                            rng.choice(doctor_ids),
                            "建议继续完善相关检查并密切监护。",
                            "必要时转专科进一步处理。",
                            visit_time + timedelta(minutes=80),
                        ),
                    )

                if is_green:
                    activate_time = visit_time + timedelta(minutes=rng.randint(2, 12))
                    metrics = {"door_to_ecg": None, "door_to_ct": None, "door_to_needle": None, "door_to_balloon": None, "door_to_surgery": None}
                    if scenario.green_type == "胸痛":
                        metrics["door_to_ecg"] = rng.randint(180, 820)
                        if rng.random() < 0.55:
                            metrics["door_to_balloon"] = rng.randint(2500, 6200)
                        else:
                            metrics["door_to_needle"] = rng.randint(1200, 2400)
                    elif scenario.green_type == "卒中":
                        metrics["door_to_ct"] = rng.randint(650, 1800)
                        metrics["door_to_needle"] = rng.randint(1800, 4100) if rng.random() < 0.45 else None
                    elif scenario.green_type == "创伤":
                        metrics["door_to_ct"] = rng.randint(780, 2500)
                        metrics["door_to_surgery"] = rng.randint(1800, 4800) if rng.random() < 0.35 else None
                    target_met = None
                    checks = []
                    if metrics["door_to_ecg"] is not None:
                        checks.append(metrics["door_to_ecg"] <= 600)
                    if metrics["door_to_ct"] is not None:
                        limit = 1500 if scenario.green_type == "卒中" else 1800
                        checks.append(metrics["door_to_ct"] <= limit)
                    if metrics["door_to_balloon"] is not None:
                        checks.append(metrics["door_to_balloon"] <= 5400)
                    if metrics["door_to_needle"] is not None:
                        checks.append(metrics["door_to_needle"] <= (1800 if scenario.green_type == "胸痛" else 3600))
                    if metrics["door_to_surgery"] is not None:
                        checks.append(metrics["door_to_surgery"] <= 3600)
                    if checks:
                        target_met = 1 if all(checks) else 0
                    active_channel = is_active and rng.random() < 0.42
                    completed_time = None if active_channel else activate_time + timedelta(minutes=rng.randint(35, 140))
                    channel_status = "进行中" if active_channel else "已完成"
                    cur.execute(
                        """
                        INSERT INTO ed_green_channel (
                            visit_id, channel_type, activate_time, activate_doctor, coordinator_nurse_id, latest_event_time,
                            door_to_ecg, door_to_needle, door_to_balloon, door_to_ct, door_to_surgery,
                            target_met, channel_outcome, channel_status, completed_time
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            visit_id,
                            scenario.green_type,
                            activate_time,
                            doctor_id,
                            rng.choice(nurse_ids),
                            completed_time or activate_time,
                            metrics["door_to_ecg"],
                            metrics["door_to_needle"],
                            metrics["door_to_balloon"],
                            metrics["door_to_ct"],
                            metrics["door_to_surgery"],
                            target_met,
                            "转入住院" if not active_channel else None,
                            channel_status,
                            completed_time,
                        ),
                    )
                    channel_id = cur.lastrowid
                    events = [("activate", f"{scenario.green_type}绿色通道启动", activate_time, 0)]
                    if metrics["door_to_ecg"] is not None:
                        events.append(("ecg", "心电图完成", activate_time + timedelta(seconds=metrics["door_to_ecg"]), metrics["door_to_ecg"]))
                    if metrics["door_to_ct"] is not None:
                        events.append(("ct", "CT完成", activate_time + timedelta(seconds=metrics["door_to_ct"]), metrics["door_to_ct"]))
                    if metrics["door_to_needle"] is not None:
                        events.append(("needle", "溶栓完成", activate_time + timedelta(seconds=metrics["door_to_needle"]), metrics["door_to_needle"]))
                    if metrics["door_to_balloon"] is not None:
                        events.append(("balloon", "球囊开通", activate_time + timedelta(seconds=metrics["door_to_balloon"]), metrics["door_to_balloon"]))
                    if metrics["door_to_surgery"] is not None:
                        events.append(("surgery", "手术开始", activate_time + timedelta(seconds=metrics["door_to_surgery"]), metrics["door_to_surgery"]))
                    if completed_time:
                        events.append(("close", "绿色通道关闭", completed_time, int((completed_time - activate_time).total_seconds())))
                    for event_type, event_name, event_time, elapsed_seconds in events:
                        cur.execute(
                            """
                            INSERT INTO ed_green_channel_event (
                                channel_id, visit_id, event_type, event_name, event_time, elapsed_seconds, recorder_id, note
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                            """,
                            (
                                channel_id,
                                visit_id,
                                event_type,
                                event_name,
                                event_time,
                                elapsed_seconds,
                                doctor_id,
                                "自动生成演示数据",
                            ),
                        )

                if triage_level == 1 and rng.random() < scenario.rescue_prob:
                    rescue_start = visit_time + timedelta(minutes=rng.randint(12, 45))
                    rescue_active = is_active and rng.random() < 0.35
                    rescue_end = None if rescue_active else rescue_start + timedelta(minutes=rng.randint(18, 96))
                    outcome = None if rescue_active else choose_weighted(rng, (("成功", 72), ("失败", 18), ("死亡", 10)))
                    cur.execute(
                        """
                        INSERT INTO ed_rescue_record (
                            visit_id, rescue_start, rescue_end, rescue_duration, rescue_leader, rescue_team, arrest_type,
                            cpr_flag, cpr_start, cpr_duration, rosc_time, airway_type, outcome, rescue_status,
                            latest_event_time, rescue_summary
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            visit_id,
                            rescue_start,
                            rescue_end,
                            int((rescue_end - rescue_start).total_seconds() // 60) if rescue_end else None,
                            doctor_id,
                            json.dumps([doctor_id, rng.choice(nurse_ids), rng.choice(nurse_ids)], ensure_ascii=False),
                            rng.choice(["室颤", "无脉性电活动", "心电静止", None]),
                            1 if rng.random() < 0.7 else 0,
                            rescue_start if rng.random() < 0.7 else None,
                            rng.randint(12, 45) if rescue_end else None,
                            rescue_start + timedelta(minutes=rng.randint(8, 28)) if outcome == "成功" and rescue_end else None,
                            rng.choice(["气管插管", "喉罩", "球囊面罩", "无创通气"]),
                            outcome,
                            "抢救中" if rescue_active else "已完成",
                            rescue_end or rescue_start,
                            "自动生成第三阶段抢救场景",
                        ),
                    )
                    rescue_id = cur.lastrowid
                    timeline_events = [
                        ("start", "抢救启动", rescue_start, None, None, None, "抢救团队到位"),
                        ("medication", "肾上腺素静推", rescue_start + timedelta(minutes=5), "肾上腺素", "1mg", "iv", "首次抢救用药"),
                    ]
                    if rng.random() < 0.5:
                        timeline_events.append(("intubation", "气道建立", rescue_start + timedelta(minutes=8), None, None, None, "完成高级气道"))
                    if rng.random() < 0.4:
                        timeline_events.append(("defibrillation", "电除颤", rescue_start + timedelta(minutes=12), None, None, None, "200J 双向波"))
                    if outcome == "成功" and rescue_end:
                        timeline_events.append(("rosc", "自主循环恢复", rescue_start + timedelta(minutes=18), None, None, None, "恢复窦性心律"))
                    if rescue_end:
                        timeline_events.append(("end", "抢救结束", rescue_end, None, None, None, "转入后续观察/专科病房"))
                    for event_type, event_name, event_time, medication_name, dose, route, note in timeline_events:
                        cur.execute(
                            """
                            INSERT INTO ed_rescue_timeline (
                                rescue_id, visit_id, event_time, event_type, event_name, performer_id,
                                medication_name, dose, route, note, vital_snapshot
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            """,
                            (
                                rescue_id,
                                visit_id,
                                event_time,
                                event_type,
                                event_name,
                                doctor_id,
                                medication_name,
                                dose,
                                route,
                                note,
                                json.dumps({"HR": vitals["hr"], "SpO2": vitals["spo2"]}, ensure_ascii=False),
                            ),
                        )

            refresh_operational_snapshot(cur, rng, now)
            bed_rebuild(cur)
            conn.commit()

            with conn.cursor() as cur2:
                cur2.execute(
                    """
                    SELECT
                        (SELECT COUNT(*) FROM patient_info) AS patient_count,
                        (SELECT COUNT(*) FROM ed_visit) AS visit_count,
                        (SELECT COUNT(*) FROM ed_order) AS order_count,
                        (SELECT COUNT(*) FROM ed_lab_order) AS lab_count,
                        (SELECT COUNT(*) FROM ed_imaging_order) AS imaging_count,
                        (SELECT COUNT(*) FROM ed_nursing_record) AS nursing_count,
                        (SELECT COUNT(*) FROM ed_green_channel) AS green_count,
                        (SELECT COUNT(*) FROM ed_green_channel_event) AS green_event_count,
                        (SELECT COUNT(*) FROM ed_rescue_record) AS rescue_count,
                        (SELECT COUNT(*) FROM ed_rescue_timeline) AS rescue_event_count,
                        (SELECT COUNT(*) FROM ed_observation) AS observation_count
                    """
                )
                summary = cur2.fetchone()
            print(json.dumps(summary, ensure_ascii=False))
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
