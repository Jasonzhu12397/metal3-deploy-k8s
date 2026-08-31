"""
Covers templates/ai/vllm-deployment.yaml.j2 rendering -- pure Jinja2 +
yaml.safe_load, no mocking needed. Checks both a minimal config (the
common case) and one exercising every optional field, since this
template's optional fields (extra_args, hf_token_secret_name) already
caught a real StrictUndefined bug once during development (bare
`{% if workload.extra_args %}` without an `is defined` guard crashes
when the key is genuinely absent, not just falsy -- the same class of
bug fixed earlier in the metal3/cloud-provider CAPI templates for
pool.reserved_cpus).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.services.yaml_generator import YamlGeneratorService  # noqa: E402

gen = YamlGeneratorService()


def test_minimal_config_renders_without_optional_fields():
    spec = {
        "name": "qwen-7b",
        "namespace": "default",
        "model_id": "Qwen/Qwen2.5-7B-Instruct",
        "gpu_count": 1,
        "replicas": 1,
    }
    docs = gen.parse_multi(gen.render_vllm_deployment(spec))
    assert [d["kind"] for d in docs] == ["Deployment", "Service"]

    deployment, service = docs
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    assert container["image"] == "vllm/vllm-openai:latest"
    assert container["command"] == ["vllm", "serve", "Qwen/Qwen2.5-7B-Instruct"]
    assert "args" not in container
    assert "env" not in container
    assert container["resources"]["limits"]["nvidia.com/gpu"] == "1"
    assert deployment["spec"]["template"]["spec"]["nodeSelector"] == {"gpu": "true"}
    assert deployment["spec"]["template"]["spec"]["volumes"][0]["emptyDir"]["sizeLimit"] == "4Gi"

    assert service["spec"]["ports"] == [{"port": 8000, "targetPort": 8000}]
    assert service["spec"]["type"] == "ClusterIP"


def test_full_config_with_every_optional_field():
    spec = {
        "name": "llama-70b",
        "namespace": "ai-workloads",
        "model_id": "meta-llama/Llama-3.1-70B-Instruct",
        "gpu_count": 4,
        "replicas": 2,
        "hf_token_secret_name": "hf-token-secret",
        "extra_args": ["--trust-remote-code", "--max-model-len", "8192"],
        "shm_size": "8Gi",
        "image_tag": "v0.11.0",
    }
    deployment, _service = gen.parse_multi(gen.render_vllm_deployment(spec))
    container = deployment["spec"]["template"]["spec"]["containers"][0]

    assert container["image"] == "vllm/vllm-openai:v0.11.0"
    assert container["args"] == ["--trust-remote-code", "--max-model-len", "8192"]
    assert container["env"] == [
        {"name": "HUGGING_FACE_HUB_TOKEN", "valueFrom": {"secretKeyRef": {"name": "hf-token-secret", "key": "token"}}}
    ]
    assert container["resources"]["limits"]["nvidia.com/gpu"] == "4"
    assert deployment["spec"]["replicas"] == 2
    assert deployment["spec"]["template"]["spec"]["volumes"][0]["emptyDir"]["sizeLimit"] == "8Gi"


def test_namespace_and_labels_consistent_across_deployment_and_service():
    spec = {
        "name": "test-model",
        "namespace": "custom-ns",
        "model_id": "facebook/opt-125m",
        "gpu_count": 1,
        "replicas": 1,
    }
    deployment, service = gen.parse_multi(gen.render_vllm_deployment(spec))

    assert deployment["metadata"]["namespace"] == "custom-ns"
    assert service["metadata"]["namespace"] == "custom-ns"
    assert deployment["spec"]["selector"]["matchLabels"] == {"app": "test-model"}
    assert service["spec"]["selector"] == {"app": "test-model"}
