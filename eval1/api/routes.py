"""Legacy import path — read routes are lightweight; write routes load langgraph."""

from eval1.api.read_routes import datasets, layer2_dialogues, router

__all__ = ["router", "datasets", "layer2_dialogues"]
