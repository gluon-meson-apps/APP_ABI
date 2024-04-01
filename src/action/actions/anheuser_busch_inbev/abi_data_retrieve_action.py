import json
import os
import sqlite3
from typing import Optional

import pandas as pd
from gluon_meson_sdk.models.abstract_models.chat_message_preparation import ChatMessagePreparation
from gluon_meson_sdk.models.scenario_model_registry.base import DefaultScenarioModelRegistryCenter
from loguru import logger

from action.base import Action, ActionResponse, ResponseMessageType, ChatResponseAnswer, GeneralResponse

NO_INFORMATION = '没有找到相关数据.'
DB_PATH = f'{os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))}/resources/repository/anheuser_busch_inbev.db'
FILE_PATH = f'{os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))}/resources/repository/files/TAG_BASIC_INFO.xlsx'

TABLES = """
Tag_Basic_Info Table(main.Tag_Basic_Info): -- Table to store data of tag basic info of Abi.
create table Tag_Basic_Info
(
    ID                  INTEGER
        primary key autoincrement, -- 数据库记录ID，主键，自增
    MOD_TYPE            TEXT    not null, -- 模型类别，示例：设备_点位模型
    FAC_DESC            TEXT    not null, -- 工厂名称，示例：佛山
    DEPAR_DESC          TEXT, -- 部门名称，示例：包装
    PROCESS_DESC        TEXT, -- 工序名称，示例：听装线
    LINE_DESC           TEXT, -- 产线名称，示例：CL1
    EQUIP_DESC          TEXT, -- 主设备名称，示例：酒机FCI
    EQUIP_NUM_DESC      INTEGER, -- 主设备序号名称，示例：1
    FUNLOC_CODE         TEXT    not null, -- 功能位置，示例：CN55302001-0501
    FUNLOC_CODE_NAME    TEXT    not null, -- 功能位置（名称），示例：佛山-包装-听装线-CL1-酒机FCI-1
    TAG_TYPE            TEXT    not null, -- 点位类型，示例：物理点位
    COL_METH            TEXT    not null, -- 采集方式，示例：自动采集
    DATA_SOUR           TEXT    not null, -- 数据来源，示例：BBX
    DATA_TRAN_METH      TEXT, -- 数据传输协议，示例：OPC UA
    DATA_CON_ADDR       TEXT, -- BBX OPCUA服务地址/PLC连接地址，示例：172.31.145.116:4847
    DATA_STOR_ADDR      TEXT, -- BBX/PLC点位地址，示例：ns=2;s=ELECTRIC.Packaging.ABI.ECS_OPC.GY13AL09_7_EA
    DATA_STOR_ADDR_CODE TEXT, -- BBX点位编码/PLC_DB地址，示例：ELECTRIC.Packaging.ABI.ECS_OPC.GY13AL09_7_EA
    PLC_IP_ADDR         TEXT, -- PLC_连接地址(选填)
    PLC_DB_ADDR         TEXT, -- PLC_DB地址(选填)
    SOURCE_TAG_DESC     TEXT, -- 数据源点位描述，示例：办公楼空调 APkt1（4323）
    DATA_SOUR_DATA_TYPE TEXT, -- 数据源数据类型，示例：Float
    IOT_COL_DATA_TYPE   TEXT, -- IOT数采数据类型，示例：Float
    DATA_REQ_FREQ       INTEGER not null, -- 需求频率(ms)，示例：5000
    MOD_DISP_NAME       TEXT    not null, -- 模型显示名称，示例：动力_供电_低压开关柜
    MOD_NAME            TEXT    not null, -- 模型名称，示例：UTL-POWS-LVSwitchingPanel
    IOT_ATTR_DISP_NAME  TEXT    not null, -- IOT属性显示名称，示例：回路7_正向有功电度-累计值
    IOT_ATTR_NAME       TEXT    not null, -- IOT属性名称，示例：LOP7_FWD_ACT_ENG-ACV
    PARA_NAME           TEXT    not null, -- 参数名称，示例：回路7_正向有功电度
    PARA_CODE           TEXT    not null, -- 参数编码，示例：LOP7_FWD_ACT_ENG
    PARA_EN_NAME        TEXT, -- 参数英文名称
    ATTR_NAME           TEXT    not null, -- 属性名称，示例：累计值
    ATTR_CODE           TEXT, -- 属性编码，示例：ACV
    ATTR_EN_NAME        TEXT, -- 属性英文名称，示例：Accumulated Value
    UNIT                TEXT, -- 单位，示例：KWH
    TAG_DATA_TYPE       TEXT, -- 模型数据类型，示例：DOUBLE
    SUB_DOMAIN          TEXT, -- 业务域细分，示例：SCF/BBL
    TAG_FUNLOC_DESC     TEXT    not null, -- 点位功能位置名称，示例：莆田-动力-供电-1-低压开关柜-1182
    TAG_FUNLOC_CODE     TEXT    not null, -- 点位功能位置编码，示例：APAC-CN55302001-0501
    TAG_NAME            TEXT    not null, -- 点位名称，示例：佛山-包装-听装线-CL1-酒机FCI-1-回路7_正向有功电度-累计值
    TAG_CODE            TEXT    not null, -- 点位编码，示例：APAC-CN55302001-0501-LOP7_FWD_ACT_ENG-ACV
    MIN                 TEXT, -- 最小值
    MAX                 TEXT, -- 最大值
    REMARK              TEXT -- 备注
);
"""

summarize_prompt = """
## 角色：语言能力专家。

## 任务：
- 根据聊天记录，总结优先级最高的问题，也就是用户最近提的问题。

## 要求：
- 请注意，对话历史后期的问题优先级高于开头的问题。
- 总结的问题需要带着相关的完整的上下文。

## 使用以下格式总结问题：
问题：{摘要问题}

## 聊天记录
{{chat_history}}
"""

reply_prompt = """
## 角色：AI助手

## 背景：作为AI助手，你协助用户查询有关ABI公司的基本信息数据。用户提出问题，这些问题几乎需要使用以下SQL查询数据库。如果查询结果不为空，你应该根据查询结果回答问题。

### 任务：根据提供的查询结果回答下面的问题。

### 要求：
- 使用专业的语气。
- 根据查询结果回答问题，如果用户要求返回的是数据，并且查询结果里也是多条包含多个键值对的实体，那么请以表格的形式返回。

## 问题：
{{question}}

## SQL
{{sql}}

### 查询结果：
{{query_result}}
"""

sql_generate_prompt = """
## 角色：软件工程AI助手

## 背景：
我们的保险索赔处理系统依赖于一个数据库，包含以下表格。

### 表格：
{{tables}}

## 任务：
根据用户提供的上下文信息生成准确的SQL查询。这些查询将允许AI助手从数据库中获取相关数据以回答下面的问题。

## 要求：
- SQL查询必须遵循表结构。
- 请仔细理解表中每个字段的含义（包括解释和示例），这将帮助你生成相应的SQL。
- 对于用户问题中的术语，如果你有不理解的地方可以参考下面给你的用户提问专用词汇数据集合，这个集合包含了数据库中相关列的数据集合，你可以据此了解哪些词汇是属于哪一列的。
    - 如果有你不理解的词汇在专用词汇数据集合没有找到类别，那可能属于PARA_NAME。
- 如果表中的字段是TEXT，在sql中的条件应该使用 LIKE '%xxx%' 而不是等于。
- sql的SELECT之后的字段值应该与问题相关，也就是用户问题中需要知道的查询目标
    - 如果有多列与用户查询的目标相关，应当一起返回，例如用户想查询功能位置，那么与功能位置相关的列包括功能位置编码与功能位置（名称），此时应该一起SELECT出来。
    - 如果用户没有明确说明需要查询的目标，生成的SQL就应该将符合条件数据行的所有列SELECT出来。

## 问题
{{question}}

## 生成的sql格式：
{generated sql}

## 用户提问专用词汇数据集合
{{data_set}}
"""

def summarize_question(chat_model, prompt, history):
    chat_message_preparation = ChatMessagePreparation()
    chat_message_preparation.add_message(
        "system",
        prompt,
        chat_history=history
    )
    chat_message_preparation.log(logger)
    summarized_question = chat_model.chat(**chat_message_preparation.to_chat_params(), max_length=2048).response
    logger.info(f"summarized_question: {summarized_question}")
    return summarized_question


def reply_question(chat_model, prompt, question, query_result, sql):
    chat_message_preparation = ChatMessagePreparation()
    chat_message_preparation.add_message("user", prompt, query_result=query_result, sql=sql, question=question)
    chat_message_preparation.log(logger)
    result = chat_model.chat(**chat_message_preparation.to_chat_params(), max_length=2048).response
    logger.info(f"chat result: {result}")
    return result


def generate_sql(chat_model, prmpt, question, tables, data_set):
    chat_message_preparation = ChatMessagePreparation()
    chat_message_preparation.add_message(
        "system",
        prmpt,
        question=question,
        tables=tables,
        data_set=data_set
    )
    chat_message_preparation.log(logger)
    sql = chat_model.chat(**chat_message_preparation.to_chat_params(), max_length=2048).response
    logger.info(f"sql: {sql}")
    return sql


def extract_data_set(file_path):
    df = pd.read_excel(file_path)

    selected_columns = [1, 2, 3, 4, 5]

    column_data_types = {}

    for column_index in selected_columns:
        abbreviation = df.columns[column_index].strip()

        description = df.iloc[0][column_index]
        data_types = set(df.iloc[1:, column_index].dropna().astype(str))

        column_data_types[abbreviation] = {'description': description, 'types': list(data_types)}
    json_string = json.dumps(column_data_types, ensure_ascii=False, indent=2)
    return json_string


def query_from_db(sql: str) -> tuple[str, Optional[Exception]]:
    con = sqlite3.connect(f'{DB_PATH}')
    cur = con.cursor()

    result, ex = NO_INFORMATION, None
    try:
        cur.execute(sql)
        rows = cur.fetchall()
        logger.info(f'rows{rows}')
        if rows:
            columns = [col[0] for col in cur.description]
            result = []

            for row in rows:
                result_dict = {columns[i]: row[i] for i in range(len(columns))}
                result.append(result_dict)
    except Exception as exception:
        ex = exception
        logger.info(f'sql execute error:\nsql:\n{sql}\nerror:{str(ex)}')
    finally:
        con.commit()
        con.close()
        logger.info(f"Query result: {result}")
        return str(result), ex


class AbiDataRetrieveAction(Action):
    def __init__(self):
        self.scenario_model_registry = DefaultScenarioModelRegistryCenter()
        self.scenario_model = self.get_name() + "_action"

    def get_name(self) -> str:
        return "abi_data_retrieve"

    async def run(self, context) -> ActionResponse:
        logger.info(f"exec action: {self.get_name()} ")
        chat_model = await self.scenario_model_registry.get_model(self.scenario_model, context.conversation.session_id)

        history = context.conversation.get_history().format_string()
        question = summarize_question(chat_model, summarize_prompt, history=history)

        data_set = extract_data_set(FILE_PATH)
        sql = generate_sql(chat_model, sql_generate_prompt, question, TABLES, data_set)

        query_result, _ = query_from_db(sql)

        result = reply_question(chat_model, reply_prompt, question, query_result, sql)
        answer = ChatResponseAnswer(
            messageType=ResponseMessageType.FORMAT_TEXT, content=result, intent=context.conversation.current_intent.name
        )
        return GeneralResponse(code=200, message="success", answer=answer, jump_out_flag=False)
