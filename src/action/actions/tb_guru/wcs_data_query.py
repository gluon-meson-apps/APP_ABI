import asyncio
import shutil
import uuid
from typing import Union

import pandas as pd
from gluon_meson_sdk.models.abstract_models.chat_message_preparation import ChatMessagePreparation
from loguru import logger

from action.base import (
    ChatResponseAnswer,
    ResponseMessageType,
    ActionResponse,
    UploadFileContentType,
    AttachmentResponse,
    Attachment,
    GeneralResponse,
)
from action.actions.tb_guru.base import TBGuruAction
from third_system.search_entity import SearchParam, SearchItem
from utils.ppt_helper import generate_ppt
from utils.common import generate_tmp_dir

ppt_filename = "tb_guru_ppt.pptx"

extract_data_prompt = """
## Role
You are an assistant with name as "TB Guru".
Help me extract data from user input and reply it with below JSON schema.

## Schema should be like this
{
    // all years data for {{company_name}} company
    "all_years_data": [{
        "company": "", // company name, should be STRING type
        "days": "", // the date for the record, should be STRING type
        "dpo": "", // DPO, should be NUMBER type,
        "dso": "", // DPO, should be NUMBER type,
        "dio": "", // DIO, should be NUMBER type,
        "ccc": "", // CCC, should be NUMBER type,
    }, ...],
    // latest year data for all companies
    "latest_year_data": [{
        "company": "", // company name, should be STRING type
        "days": "", // the date for the record, should be STRING type
        "dpo": "", // DPO, should be NUMBER type,
        "dso": "", // DPO, should be NUMBER type,
        "dio": "", // DIO, should be NUMBER type,
        "ccc": "", // CCC, should be NUMBER type,
    }, ...]
}

## User input
{{user_input}}

## Instruction
Please reply the formatted JSON data.
"""

user_prompt = """
## User question
{{user_input}}
Please IGNORE my requirements for PPT and DO NOT mention anything about PPT in your reply.
"""

ppt_prompt = """
## Info
{{info}}

## Requirements
You are an assistant with name as "TB Guru".
You have generated a PPT for the user and the link is attached below, tell the user to download it.
If the PPT link is empty, ask the user to check if their input question is valid.

## PPT link
{{ppt_link}}

## Instruction
now, reply your result with above info.
"""


async def extract_data(context, chat_model, company_name) -> tuple[list[SearchItem], list[SearchItem]]:
    chat_message_preparation = ChatMessagePreparation()
    chat_message_preparation.add_message(
        "system",
        extract_data_prompt,
        company_name=company_name,
        user_input=context.conversation.current_user_input,
    )
    chat_message_preparation.log(logger)

    formatted_data = (
        await chat_model.achat(
            **chat_message_preparation.to_chat_params(), max_length=1024, sub_scenario="data_provided"
        )
    ).get_json_response()
    current_company_data = (
        formatted_data["all_years_data"] if formatted_data and "all_years_data" in formatted_data else []
    )
    latest_all_data = (
        formatted_data["latest_year_data"] if formatted_data and "latest_year_data" in formatted_data else []
    )
    logger.info(f"formatted data: {formatted_data}")
    return [SearchItem(meta__score=-1, **d) for d in latest_all_data], [
        SearchItem(meta__score=-1, **d) for d in current_company_data
    ]


def parse_model_to_dataframe(data):
    df = pd.DataFrame([w.model_dump() for w in data])
    df = df.sort_values(by="days", ascending=False) if "days" in df.columns else df
    return df


class WcsDataQuery(TBGuruAction):
    def __init__(self):
        super().__init__()
        self.tmp_file_dir = generate_tmp_dir("wcs")

    def get_name(self) -> str:
        return "wcs_data_query"

    async def _generate_ppt_link(
        self, df_current: pd.DataFrame, df_all: pd.DataFrame, insight: str
    ) -> Union[Attachment, None]:
        files_dir = f"{self.tmp_file_dir}/{str(uuid.uuid4())}"
        ppt_path = generate_ppt(df_current, df_all, insight, files_dir)
        if ppt_path:
            attachment = Attachment(name="tb_guru_ppt.pptx", path=ppt_path, content_type=UploadFileContentType.PPTX)
            links = await self.unified_search.upload_files_to_minio([attachment])
            shutil.rmtree(files_dir)
            attachment.url = links[0] if links else ""
            return attachment
        return None

    async def _search_db(self, entity_dict, session_id) -> tuple[list[SearchItem], list[SearchItem]]:
        query_list = [
            f"""Query WCS data with days as {entity_dict["days"]}:"""
            if "days" in entity_dict
            else "Query WCS data sort by days descending:"
        ]
        if "company" in entity_dict:
            query_list.append(f"""Query WCS data with company {entity_dict["company"]}:""")
        tasks = [self.unified_search.search(SearchParam(query=q), session_id) for q in query_list]
        search_res = await asyncio.gather(*tasks)
        items = [s[0].items if s else [] for s in search_res]
        all_companies_data, current_company_data = items[0], items[1] if len(items) > 1 else []
        return all_companies_data, current_company_data

    async def run(self, context) -> ActionResponse:
        chat_model = await self.scenario_model_registry.get_model(self.scenario_model, context.conversation.session_id)
        logger.info(f"exec action: {self.get_name()} ")

        entity_dict = context.conversation.get_simplified_entities()
        is_ppt_output = entity_dict["is_ppt_output"] if "is_ppt_output" in entity_dict else False
        is_data_provided = entity_dict["is_data_provided"] if "is_data_provided" in entity_dict else False
        company_name = entity_dict["company"] if "company" in entity_dict else ""

        if is_data_provided:
            latest_all_data, current_company_data = (
                await extract_data(context, chat_model, company_name) if is_ppt_output and company_name else ([], [])
            )
        else:
            latest_all_data, current_company_data = await self._search_db(entity_dict, context.conversation.session_id)

        df_current_company = parse_model_to_dataframe(current_company_data)
        df_all_companies = parse_model_to_dataframe(latest_all_data)

        chat_message_preparation = ChatMessagePreparation()
        chat_message_preparation.add_message(
            "user",
            user_prompt,
            user_input=context.conversation.current_user_input,
        )
        df_non_duplicate = pd.concat([df_current_company, df_all_companies], ignore_index=True).drop_duplicates(
            subset=["id"]
        )
        if not is_data_provided:
            chat_message_preparation.add_message(
                "assistant",
                """## WCS data are extracted already\n{{wcs_data}}""",
                wcs_data=df_non_duplicate.drop(
                    columns=["meta__score", "meta__reference", "id"], errors="ignore"
                ).to_string(),
            )
        chat_message_preparation.log(logger)

        info_result = (
            await chat_model.achat(**chat_message_preparation.to_chat_params(), max_length=1024, sub_scenario="insight")
        ).response
        logger.info(f"chat result: {info_result}")

        final_result = info_result
        ppt_attachment = None
        if is_ppt_output:
            ppt_attachment = await self._generate_ppt_link(df_current_company, df_all_companies, info_result)

            chat_message_preparation = ChatMessagePreparation()
            chat_message_preparation.add_message("system", ppt_prompt, ppt_link=ppt_attachment, info=info_result)
            chat_message_preparation.log(logger)

            final_result = (
                await chat_model.achat(**chat_message_preparation.to_chat_params(), max_length=1024, sub_scenario="ppt")
            ).response

        logger.info(f"final result: {final_result}")

        answer = ChatResponseAnswer(
            messageType=ResponseMessageType.FORMAT_TEXT,
            content=final_result,
            intent=context.conversation.current_intent.name,
            references=[]
            if is_data_provided
            else [SearchItem(**d) for d in df_non_duplicate.to_dict(orient="records")],
        )
        if ppt_attachment:
            return AttachmentResponse(
                code=200, message="success", answer=answer, jump_out_flag=False, attachments=[ppt_attachment]
            )
        return GeneralResponse(code=200, message="success", answer=answer, jump_out_flag=False)


if __name__ == "__main__":
    file_dir = generate_tmp_dir("wcs")
    with open(f"{file_dir}/test.txt", "w") as f:
        f.write("test")
