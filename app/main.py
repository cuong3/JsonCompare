import json
from pathlib import Path

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .compare import DEFAULT_KEY_FIELDS, OUTPUT_FIELDS, compare_files

APP_DIR = Path(__file__).resolve().parent
app = FastAPI(title="JsonCompare")
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")
templates = Jinja2Templates(directory=APP_DIR / "templates")


def _parse_upload(file: UploadFile) -> list[dict]:
    raw = file.file.read()
    data = json.loads(raw)
    if not isinstance(data, list):
        raise ValueError(f"{file.filename} is not a JSON array")
    return data


@app.get("/", response_class=HTMLResponse)
async def upload_page(request: Request):
    return templates.TemplateResponse(request, "upload.html", {
        "default_key_fields": DEFAULT_KEY_FIELDS,
        "default_output_fields": OUTPUT_FIELDS,
    })


@app.post("/compare", response_class=HTMLResponse)
async def compare_page(
    request: Request,
    left_file: UploadFile = File(...),
    right_file: UploadFile = File(...),
    key_fields: list[str] = Form(list(DEFAULT_KEY_FIELDS)),
    output_fields: list[str] = Form(list(OUTPUT_FIELDS)),
    show: str = Form("all"),
):
    try:
        left = _parse_upload(left_file)
        right = _parse_upload(right_file)
    except (json.JSONDecodeError, ValueError) as exc:
        return templates.TemplateResponse(request, "upload.html", {
            "error": str(exc),
            "default_key_fields": DEFAULT_KEY_FIELDS,
            "default_output_fields": OUTPUT_FIELDS,
        })

    result = compare_files(left, right, tuple(key_fields), tuple(output_fields))

    # Apply show filter
    if show == "changed":
        result["rows"] = [r for r in result["rows"] if r["changed"]]
    elif show == "added":
        result["rows"] = [r for r in result["rows"] if r["type"] == "added"]
    elif show == "removed":
        result["rows"] = [r for r in result["rows"] if r["type"] == "removed"]
    # else "all" — no filtering

    return templates.TemplateResponse(request, "compare.html", {
        "result": result,
        "output_fields": tuple(output_fields),
        "left_name": left_file.filename,
        "right_name": right_file.filename,
        "show": show,
    })


@app.post("/api/compare")
async def api_compare(
    left_file: UploadFile = File(...),
    right_file: UploadFile = File(...),
    key_fields: list[str] = Form(list(DEFAULT_KEY_FIELDS)),
    output_fields: list[str] = Form(list(OUTPUT_FIELDS)),
):
    try:
        left = _parse_upload(left_file)
        right = _parse_upload(right_file)
    except (json.JSONDecodeError, ValueError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

    result = compare_files(left, right, tuple(key_fields), tuple(output_fields))
    return result
