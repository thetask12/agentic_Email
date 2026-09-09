from fastapi import APIRouter, HTTPException

from app.repositories.repositories import email_template_repo, follow_up_template_repo
from app.schemas.requests import TemplateCreateRequest, TemplateUpdateRequest
from app.utils.ids import new_id

router = APIRouter(prefix="/api", tags=["templates"])


@router.get("/email-templates")
async def list_templates():
    items = await email_template_repo.list_all()
    return {"items": items, "total": len(items)}


@router.post("/email-templates")
async def create_template(req: TemplateCreateRequest):
    return await email_template_repo.create({"template_id": new_id("template"), **req.model_dump()})


@router.patch("/email-templates/{template_id}")
async def update_template(template_id: str, req: TemplateUpdateRequest):
    existing = await email_template_repo.get_by_id(template_id)
    if not existing:
        raise HTTPException(404, "Template not found")
    patch = {k: v for k, v in req.model_dump().items() if v is not None}
    return await email_template_repo.update(template_id, patch)


@router.post("/email-templates/{template_id}/duplicate")
async def duplicate_template(template_id: str):
    existing = await email_template_repo.get_by_id(template_id)
    if not existing:
        raise HTTPException(404, "Template not found")
    copy = dict(existing)
    copy["template_id"] = new_id("template")
    copy["name"] = f"{existing.get('name', 'Template')} (copy)"
    copy["is_default"] = False
    return await email_template_repo.create(copy)


@router.delete("/email-templates/{template_id}")
async def delete_template(template_id: str):
    existing = await email_template_repo.get_by_id(template_id)
    if not existing:
        raise HTTPException(404, "Template not found")
    await email_template_repo.update(template_id, {"is_active": False})
    return {"deleted": True}


@router.get("/follow-up-templates")
async def list_fu_templates():
    items = await follow_up_template_repo.list_all()
    return {"items": items, "total": len(items)}


@router.post("/follow-up-templates")
async def create_fu_template(name: str, sequence_number: int, subject: str, body: str):
    return await follow_up_template_repo.create({
        "template_id": new_id("template"), "name": name, "sequence_number": sequence_number,
        "subject": subject, "body": body, "is_active": True,
    })
