from gluon_meson_sdk.models.abstract_models.chat_message_preparation import ChatMessagePreparation
from loguru import logger

from action.base import (
    Action,
    ActionResponse,
    ResponseMessageType,
    ChatResponseAnswer,
    AttachmentResponse,
    Attachment,
    UploadFileContentType,
)
from gluon_meson_sdk.models.scenario_model_registry.base import DefaultScenarioModelRegistryCenter

from action.df_processor import DfProcessor
from third_system.search_entity import SearchParam, SearchResponse
from third_system.unified_search import UnifiedSearch
from tracker.context import ConversationContext

prompt = """## Role
you are a chatbot, you need to answer the question from user

## context

{{context_info}}

## user input

{{user_input}}

## INSTRUCT

based on the context, answer the question;

"""


class FileBatchAction(Action):
    def __init__(self):
        self.unified_search: UnifiedSearch = UnifiedSearch()
        self.df_processor: DfProcessor = DfProcessor()
        self.scenario_model_registry = DefaultScenarioModelRegistryCenter()
        self.scenario_model = self.get_name() + "_action"

    def get_name(self) -> str:
        return "file_batch_qa"

    def get_function_with_chat_model(self, chat_model, tags, conversation):
        def get_result_from_llm(question, index):
            response: list[SearchResponse] = self.unified_search.search(
                SearchParam(query=question, tags=tags), conversation.session_id
            )
            logger.info(f"search response: {response}")
            context_info = "can't find any result"
            source_name = ""
            result = ""
            if len(response) == 0:
                return result, context_info, source_name

            first_result = response[0].items[0]
            faq_answer_column = "meta__answers"
            # todo: if faq score is too low should drop it.
            if faq_answer_column in first_result.meta__reference.model_extra:
                result = first_result.meta__reference.model_extra[faq_answer_column]
                context_info = first_result.model_extra["text"]
                source_name = first_result.meta__reference.meta__source_name
            else:
                context_info = "\n".join([item.model_dump_json() for item in response])
                chat_message_preparation = ChatMessagePreparation()
                chat_message_preparation.add_message(
                    "system",
                    prompt,
                    context_info=context_info,
                    user_input=question,
                )
                chat_message_preparation.log(logger)

                result = chat_model.chat(
                    **chat_message_preparation.to_chat_params(), max_length=2048, sub_scenario=index
                ).response
                logger.info(f"chat result: {result}")

                source_name = "\n".join(
                    {item.meta__reference.meta__source_name for one_response in response for item in one_response.items}
                )

            return result, context_info, source_name

        return get_result_from_llm

    async def run(self, context) -> ActionResponse:
        logger.info(f"exec action: {self.get_name()} ")

        conversation: ConversationContext = context.conversation
        tags = conversation.get_simplified_entities()
        logger.info(f"tags: {tags}")
        df = self.df_processor.search_items_to_df(conversation.uploaded_file_contents[0].items)

        chat_model = self.scenario_model_registry.get_model(self.scenario_model, conversation.session_id)
        get_result_from_llm = self.get_function_with_chat_model(chat_model, {"basic_type": "faq", **tags}, conversation)
        df[["answers", "reference_data", "reference_name"]] = df.reset_index().apply(
            lambda row: get_result_from_llm(row["questions"], row["index"]), axis=1, result_type="expand"
        )
        df = df[["questions", "answers", "reference_name", "reference_data"]]

        answer = ChatResponseAnswer(
            messageType=ResponseMessageType.FORMAT_TEXT,
            content="Already replied all questions in file",
            intent=conversation.current_intent.name,
        )

        file_name = f"{conversation.session_id}.csv"
        file_path = f"/tmp/{file_name}"
        content_type = UploadFileContentType.CSV
        df.to_csv(file_path, index=False)
        files = [
            ("files", (file_name, open(file_path), content_type)),
        ]
        urls = self.unified_search.upload_file_to_minio(files)
        attachment = Attachment(path=file_path, name=file_name, content_type=content_type, url=urls[0])

        return AttachmentResponse(
            code=200, message="success", answer=answer, jump_out_flag=False, attachment=attachment
        )
