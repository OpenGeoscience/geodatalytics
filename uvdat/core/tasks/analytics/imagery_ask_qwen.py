from __future__ import annotations

import base64

from celery import shared_task
from django.conf import settings
from django_large_image import utilities
import large_image

from uvdat.core.models import RasterData, TaskResult

from .analysis_type import AnalysisInputError, AnalysisTask, AnalysisType

ENDPOINT_NAMESPACE = "Kitware"
ENDPOINT_NAME = "qwen3-5-9b-gguf-ulh"
MODEL_CARD_URL = "https://huggingface.co/unsloth/Qwen3.5-9B-GGUF"
SYSTEM_PROMPT = (
    "You are an urban planning and geospatial analysis expert specializing in "
    "land use patterns, hydrology, transportation networks, and municipal policy. "
    "Analyze the provided imagery to answer the user's question. In your answer, "
    "assume that the user is also a geospatial analyst with the same expertise."
)
TOKEN_RANGE = {"min": 1000, "max": 10000, "step": 1000}
THUMBNAIL_SIZE = 4000
MAX_STARTUP_WAIT = 300


class ImageryAskQwen(AnalysisType):
    def __init__(self):
        super().__init__()
        self.name = "Imagery: Ask Qwen"
        self.description = "Select an imagery layer and ask Qwen 3.5 about it."
        self.details = (
            "Inferencing with unsloth/Qwen3.5-9B-GGUF provided by a "
            "Kitware-hosted Huggingface Inference Endpoint. "
            f"See the model card at {MODEL_CARD_URL}. "
            "Responses may cut off mid-sentence if max_tokens is reached."
        )
        self.db_value = "imagery_ask_qwen"
        self.input_types = {
            "imagery": "RasterData",
            "text_prompt": "string",
            "max_tokens": "number",
        }
        self.output_types = {
            "response": "markdown",
        }
        self.attribution = "Unsloth AI, Kitware Inc."

    @classmethod
    def is_enabled(cls) -> bool:
        return settings.UVDAT_ENABLE_IMAGERY_ASK_QWEN and settings.UVDAT_HF_TOKEN is not None

    def get_input_options(self):
        return {
            "imagery": RasterData.objects.filter(dataset__category="imagery"),
            "text_prompt": [],
            "max_tokens": [TOKEN_RANGE],
        }

    def validate_inputs(self, inputs):
        super().validate_inputs(inputs)
        try:
            imagery = RasterData.objects.get(id=inputs.get("imagery"))
        except RasterData.DoesNotExist as e:
            err_msg = "Imagery raster does not exist."
            raise AnalysisInputError(err_msg) from e
        if imagery.dataset.category != "imagery":
            err_msg = 'Selected raster is not categorized as "imagery".'
            raise AnalysisInputError(err_msg)
        max_tokens = int(inputs.get("max_tokens"))
        if max_tokens < TOKEN_RANGE["min"] or max_tokens > TOKEN_RANGE["max"]:
            err_msg = f"max_tokens must be between {TOKEN_RANGE['min']} and {TOKEN_RANGE['max']}."
            raise AnalysisInputError(err_msg)

    def run_task(self, *, project, **inputs):
        text_prompt = inputs.get("text_prompt")
        result = TaskResult.objects.create(
            name=text_prompt[:250],
            task_type=self.db_value,
            inputs=inputs,
            project=project,
            status="Initializing Task...",
        )
        imagery_ask_qwen.delay(result.id)
        return result

    def finalize(self, result):
        pass


@shared_task(base=AnalysisTask)
def imagery_ask_qwen(result_id):
    # Only available with [tasks] extra
    from huggingface_hub import (  # noqa: PLC0415
        InferenceEndpointTimeoutError,
        get_inference_endpoint,
    )

    result = TaskResult.objects.get(id=result_id)
    imagery = RasterData.objects.get(id=result.inputs.get("imagery"))
    text_prompt = result.inputs.get("text_prompt")
    max_tokens = int(result.inputs.get("max_tokens"))

    result.write_status("Encoding imagery...")
    imagery_path = utilities.field_file_to_local_path(imagery.cloud_optimized_geotiff)
    src = large_image.open(imagery_path)
    thumbnail_bytes, _ = src.getThumbnail(THUMBNAIL_SIZE, THUMBNAIL_SIZE, encoding="PNG")
    thumbnail_b64 = base64.b64encode(thumbnail_bytes).decode("utf-8")
    thumbnail_uri = f"data:image/jpeg;base64,{thumbnail_b64}"

    result.write_status("Starting inference endpoint...")
    endpoint = get_inference_endpoint(
        name=ENDPOINT_NAME,
        namespace=ENDPOINT_NAMESPACE,
        token=settings.UVDAT_HF_TOKEN,
    )
    endpoint.resume()
    try:
        endpoint.wait(timeout=MAX_STARTUP_WAIT)
    except InferenceEndpointTimeoutError:
        result.write_error("Endpoint failed to start in 5 minutes. Try again later.")
        return

    result.write_status("Sending question to Qwen...")
    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": thumbnail_uri}},
                {"type": "text", "text": text_prompt},
            ],
        },
    ]

    result.write_status("Awaiting Qwen's response...")
    chat = endpoint.client.chat_completion(
        model="unsloth/Qwen3.5-9B-GGUF",
        messages=messages,
        max_tokens=max_tokens,
    )
    response = ""
    for choice in chat.choices:
        if choice.finish_reason == "length":
            # max tokens exceeded, use reasoning content
            response += choice.message.reasoning_content
        else:
            response += choice.message.content
    result.write_outputs({"response": response})
