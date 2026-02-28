"""Components module for Indexing Service."""

# Import all components to trigger registration
import app.components.chunkers.fixed  # noqa: F401
import app.components.chunkers.recursive  # noqa: F401
import app.components.chunkers.sentence  # noqa: F401
import app.components.chunkers.semantic  # noqa: F401
import app.components.chunkers.multimodal  # noqa: F401

import app.components.providers.dashscope  # noqa: F401
import app.components.providers.bgem3  # noqa: F401
import app.components.providers.vlm  # noqa: F401

import app.components.processors.image  # noqa: F401
