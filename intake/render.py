#!/usr/bin/env python3
"""Render the intake manifest with a real image and HTTPS host; no secrets are written."""

import argparse
from pathlib import Path
import re


DNS_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")
IMAGE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/:@-]+\Z")
K8S_NAME = re.compile(r"[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?\Z")


def render(host, image, tls_secret, ingress_class=""):
    if (len(host) > 253 or len(host.split(".")) < 2 or
            any(not DNS_LABEL.fullmatch(label) for label in host.split(".")) or
            host.endswith(".invalid")):
        raise ValueError("host must be a real DNS name")
    if not IMAGE.fullmatch(image) or "replace-me" in image:
        raise ValueError("image must be a concrete registry image")
    if not K8S_NAME.fullmatch(tls_secret):
        raise ValueError("tls-secret must be a Kubernetes name")
    if ingress_class and not K8S_NAME.fullmatch(ingress_class):
        raise ValueError("ingress-class must be a Kubernetes name")
    template = (Path(__file__).parent / "k8s" / "app.yaml").read_text()
    result = (template.replace("intake.example.invalid", host)
                      .replace("registry.example.invalid/agent-eval-intake:replace-me", image)
                      .replace("agent-eval-intake-tls", tls_secret))
    if ingress_class:
        result = result.replace("spec:\n  tls:\n", f"spec:\n  ingressClassName: {ingress_class}\n  tls:\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--tls-secret", required=True)
    parser.add_argument("--ingress-class", default="")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = render(args.host, args.image, args.tls_secret, args.ingress_class)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as output:
        output.write(result)
    print(args.output)


if __name__ == "__main__":
    main()
