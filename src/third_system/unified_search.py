import aiohttp
from loguru import logger

from third_system.BusinessException import UnifiedSearchClientException
from action.base import UploadFileContentType
from third_system.search_entity import SearchParam, SearchResponse
import requests


def handle_response(response) -> SearchResponse:
    if response.status_code != 200:
        logger.error(f"{response.status_code}: {response.text}")
        return []
    print(response.json())
    return SearchResponse.model_validate(response.json())


async def handle_aio_response(response) -> SearchResponse:
    if response.status != 200:
        logger.error(f"{response.status}: {await response.text}")
        return []
    print(await response.json())
    return SearchResponse.model_validate(await response.json())


def error_handler(exception):
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                print(f"An error occurred: {e}")
                raise exception

        return wrapper

    return decorator


class UnifiedSearch:
    def __init__(self):
        self.base_url = "http://localhost:8000"

    @error_handler(UnifiedSearchClientException("unified search error", error_code=1001))
    def search(self, search_param: SearchParam) -> list[SearchResponse]:
        response = requests.post(self.base_url + "/search", json=search_param.dict())
        print(response.json())
        return [SearchResponse.parse_obj(item) for item in response.json()]

    def vector_search(self, search_param: SearchParam, table) -> list[SearchResponse]:
        response = requests.post(f"{self.base_url}/vector/{table}/search/", json=search_param.dict())
        print(response.json())
        return [handle_response(response)]

    def upload_intents_examples(self, table, intent_examples):
        response = requests.post(f"{self.base_url}/vector/{table}/intent_examples", json=intent_examples)

        return handle_response(response)

    def search_for_intent_examples(self, table, user_input):
        response = requests.post(url=f"{self.base_url}/vector/{table}/search", json={"query": user_input})

        return handle_response(response)

    def download_file_from_minio(self, file_url: str) -> SearchResponse:
        response = requests.get(url=f"{self.base_url}/file/download", params={"file_url": file_url})

        return handle_response(response)

    async def adownload_file_from_minio(self, file_url: str) -> SearchResponse:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.base_url}/file/download", params={"file_url": file_url}) as resp:
                return await handle_aio_response(resp)

    def upload_file_to_minio(self, files) -> list[str]:
        response = requests.post(url=f"{self.base_url}/file", files=files)
        return response.json()


if __name__ == "__main__":
    files = [
        (
            "files",
            ("test.txt", open("../resources/prompt_templates/slot_confirm.txt", "rb"), UploadFileContentType.TXT),
        ),
    ]
    print(UnifiedSearch().upload_file_to_minio(files))

    UnifiedSearch().search(
        SearchParam(
            query="Hi TB Guru, please help me to cross check the standard pricing of ACH payment in Singapore and see if I can offer a unit rate of SGD 0.01 to the client."
        )
    )
