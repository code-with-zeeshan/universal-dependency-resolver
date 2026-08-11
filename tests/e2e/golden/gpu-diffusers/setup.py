from setuptools import setup

_deps = [
    "filelock>=3.13.1,<3.16.0",
    "huggingface-hub>=0.27.0,<1.0",
    "importlib-metadata",
    "numpy",
    "regex!=2019.12.17",
    "requests>=2.32.2,==2.*",
    "safetensors>=0.4.3,<1.0.0",
    "httpx>=0.27.2,<1.0.0",
    "Pillow",
    "protobuf>=3.20.3,<4",
    "tensorboard",
    "pytest",
    "pytest-timeout",
    "requests-mock",
    "sentencepiece",
    "scipy",
    "tiktoken",
    "torchsde>=0.2.5,<0.3.0",
    "torch>=2.6",
    "torchvision",
    "transformers",
    "phonemizer",
    "accelerate",
    "datasets",
    "Jinja2",
    "peft",
    "timm",
]

deps = {}


def deps_list(*pkgs):
    return [deps[p] for p in pkgs]


deps = {
    p.split(" ")[0]
    .replace(",", "")
    .replace(">=", "")
    .replace("<", "")
    .replace("=", "")
    .replace("!", "")
    .strip(): p
    for p in _deps
}
# simpler: name -> spec map
deps = {
    "filelock": ">=3.13.0,<3.16.0",
    "huggingface-hub": ">=0.27.0,<1.0",
    "importlib-metadata": None,
    "numpy": None,
    "regex": "!=2019.12.17",
    "requests": ">=2.32.0,==2.*",
    "safetensors": ">=0.4.3,<1.0.0",
    "httpx": ">=0.27.2,<1.0.0",
    "Pillow": None,
    "protobuf": ">=3.20.3,<4",
    "tensorboard": None,
    "pytest": None,
    "sentencepiece": None,
    "scipy": None,
    "tiktoken": None,
    "torchsde": ">=0.2.5,<0.3.0",
    "torch": ">=2.6",
    "torchvision": None,
    "transformers": None,
    "phonemizer": None,
    "accelerate": None,
    "datasets": None,
    "Jinja2": None,
    "peft": None,
    "timm": None,
}

extras = {}
extras["quality"] = (
    deps_list("black", "isort", "ruff")
    if False
    else ["black>=22.0.0", "isort>=5.5.4", "ruff>=0.2.0"]
)
extras["training"] = deps_list(
    "accelerate", "datasets", "protobuf", "tensorboard", "Jinja2", "peft", "timm"
)
extras["torch"] = deps_list("torch")
extras["torchvision"] = deps_list("torchvision")
extras["test"] = deps_list(
    "pytest",
    "pytest-timeout",
    "requests-mock",
    "sentencepiece",
    "scipy",
    "tiktoken",
    "torchsde",
    "phonemizer",
)
extras["dev"] = extras["quality"] + extras["test"] + extras["training"]

install_requires = [
    "importlib-metadata",
    "filelock>=3.13.0,<3.16.0",
    "httpx>=0.27.2,<1.0.0",
    "huggingface-hub>=0.27.0,<1.0",
    "numpy",
    "regex!=2019.12.17",
    "requests>=2.32.0,==2.*",
    "safetensors>=0.4.3,<1.0.0",
    "Pillow",
]

setup(
    name="example-diffusers",
    version="0.1.0",
    install_requires=install_requires,
    extras_require=extras,
)
