from loguru import logger

from action.base import Action, ActionResponse, ResponseMessageType, ChatResponseAnswer, GeneralResponse
from scenario_model_registry.base import DefaultScenarioModelRegistryCenter
from third_system.search_entity import SearchParam
from third_system.unified_search import UnifiedSearch


prompt = """## Role
you are a chatbot, you need to check whether the issuing bank is in the counterparty bank list, and whether there is RMA with HSBC Singapore

## steps

1. check whether the issuing bank is in the counterparty bank list

2. if the issuing bank is not , then reply it's not compliant and answer the user with something like this:

the $bank cannot be found in the Counterparty Bank file, and that they should do further checks.

3. if the issuing bank is in the counterparty bank list 

4. check the issuing bank has RMA arrangement

5. if user is asking about RMA, then just reply the result

6. if user is asking about the HSBC is able to accept a letter of credit from that issuing bank , then you need to 
check whether the bank's counterparty type is FIG Client or HSBC Group or Network Bank. if not, then reply
we are not able to accept a letter of credit from the $bank


## all banks info

{all_banks}

## bank to be check info\n

{bank_info}

## user input

{user_input}

## INSTRUCT

now, answer the question step by step, and reply the final result
"""

summary_prompt_template = """## Role 
you are a chatbot, you need to check whether the issuing bank is in the counterparty bank list

## INSTRUCTION
currently you should summary the result of the conversation, and the result should contains the following information:

{entities}

## chat history

{chat_history}

"""



class LetterOfCreditAdvisingAction(Action):
    def __init__(self):
        self.unified_search = UnifiedSearch()
        self.scenario_model_registry = DefaultScenarioModelRegistryCenter()
        self.scenario_model = self.get_name() + "_action"

    def get_name(self) -> str:
        return 'letter_of_credit_advising'

    def run(self, context) -> ActionResponse:
        logger.info(f'exec action: {self.get_name()} ')
        chat_model = self.scenario_model_registry.get_model(self.scenario_model)

        summary_prompt = summary_prompt_template.format(entities='\n'.join([entity.json() for entity in context.conversation.get_entities()]), chat_history=context.conversation.get_history().format_string())
        result = chat_model.chat(summary_prompt, max_length=1024).response
        logger.info(f'search query: {result}')

        response = self.unified_search.search(SearchParam(query=result))
        logger.info(f'search response: {response}')
        all_banks = '\n'.join([item.json() for item in response])
        bank_info = [dict(
            field=entity.type,
            value=entity.value,
            # description=entity.description
        ) for entity in context.conversation.get_entities()]
        final_prompt = prompt.format(all_banks=all_banks, bank_info=bank_info, user_input=context.conversation.current_user_input)
        logger.info(f'final prompt: {final_prompt}')
        result = chat_model.chat(final_prompt, max_length=2048).response
        logger.info(f'chat result: {result}')

        answer = ChatResponseAnswer(messageType=ResponseMessageType.FORMAT_TEXT, content=result, intent=context.conversation.current_intent.name)
        return GeneralResponse(code=200, message='success', answer=answer, jump_out_flag=False)