from html import escape

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.services.presence_service import PresenceCampaignService

router = APIRouter(prefix="/presence", tags=["presence"])


class PresencePublicResponse(BaseModel):
    decision: str = Field(pattern="^(confirmed|available|unavailable)$")
    reason: str | None = Field(default=None, max_length=500)


@router.get("/respond/{token}", response_class=HTMLResponse)
async def show_response_page(token: str, decision: str = "confirmed") -> HTMLResponse:
    selected = decision if decision in {"confirmed", "available", "unavailable"} else "confirmed"
    titles = {
        "confirmed": "Confirmer ma disponibilité",
        "available": "Préciser mes créneaux disponibles",
        "unavailable": "Signaler une indisponibilité",
    }
    title = titles[selected]
    if selected == "available":
        reason_field = (
            '<label>Créneaux disponibles'
            '<textarea id="reason" maxlength="500" rows="4" required '
            'placeholder="lundi 08h-12h; mardi 14h-18h"></textarea></label>'
        )
    elif selected == "unavailable":
        reason_field = (
            '<label>Motif ou précision<textarea id="reason" maxlength="500" '
            'rows="4"></textarea></label>'
        )
    else:
        reason_field = ""
    safe_token = escape(token, quote=True)
    return HTMLResponse(
        f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>
body{{font-family:system-ui;background:#f5f7fc;color:#14234f;margin:0;padding:24px}}
main{{max-width:520px;margin:8vh auto;background:#fff;border:1px solid #d5dbea;border-radius:20px;padding:28px;box-shadow:0 15px 45px #14234f18}}
h1{{font-size:1.6rem}}p{{line-height:1.6;color:#58627c}}label{{display:block;font-weight:600;margin:18px 0}}textarea{{display:block;width:100%;box-sizing:border-box;margin-top:8px;border:1px solid #d5dbea;border-radius:12px;padding:12px}}
button{{border:0;border-radius:12px;background:#d84a08;color:#fff;padding:12px 18px;font-weight:700;cursor:pointer}}#result{{margin-top:16px;font-weight:600}}
</style></head><body><main><h1>{title}</h1>
<p>Cette page concerne une version précise de l’emploi du temps. Aucune réponse n’est enregistrée avant votre confirmation ci-dessous.</p>
{reason_field}<button id="submit">Valider ma réponse</button><div id="result"></div>
<script>
document.getElementById('submit').onclick=async()=>{{
 const reason=document.getElementById('reason')?.value||null;
 if('{selected}'==='available'&&!reason){{document.getElementById('result').textContent='Précisez au moins un créneau.';return;}}
 const response=await fetch('/presence/respond/{safe_token}',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{decision:'{selected}',reason}})}});
 const data=await response.json();
 document.getElementById('result').textContent=response.ok?'Réponse enregistrée. Merci.':(data.detail||'Échec de l’enregistrement.');
 if(response.ok) document.getElementById('submit').disabled=true;
}};
</script></main></body></html>"""
    )


@router.post("/respond/{token}")
async def record_public_response(
    token: str,
    body: PresencePublicResponse,
    session: AsyncSession = Depends(get_db),
) -> dict:
    try:
        return await PresenceCampaignService(session).record_response(
            token,
            decision=body.decision,
            channel="email_link",
            response_text=body.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
