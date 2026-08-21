"""What the person running this instance needs to know about it (UC-8.2).

Thin, and a manager because a Client may not reach resource access. It exists so an
operator's first two questions — is a model configured, and does it answer — have an
answer that is not "try an import and read the failure".
"""

from quookly.access import model as inference
from quookly.contracts.inference import InferenceStatusView


async def inference_status() -> InferenceStatusView:
    """What this instance is pointed at, and whether it answers."""
    probed = await inference.probe()
    return InferenceStatusView(
        configured=probed.configured,
        base_url=probed.base_url,
        model=probed.model,
        authenticated=probed.authenticated,
        reachable=probed.reachable,
        detail=probed.detail,
    )
