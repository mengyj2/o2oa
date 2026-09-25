#!/usr/bin/env python3
"""
Ingest O2OA runtime service descriptors from /o2_core/o2/xAction/services/*.json
into the local data.db vector KB, category o2oa_api.

Each .json file under the services dir becomes one doc in the KB with id format:
  o2kb::o2oa_api::<ActionName>

We strip // and /* */ comments, parse the resulting JSON, and use the module name
to construct a readable action name for the doc ID.
"""

import os, json, re, httpx, sys

BASE = r"D:/O2OA/o2server/servers/webServer/o2_core/o2/xAction/services"
CATEGORY = "o2oa_api"
TOKEN = "local-o2-agent-2026"

# Map each service module filename to a readable action name for the doc ID.
MODULE_TO_ACTION = {
    "x_attendance_assemble_control":  "AttendanceAction",
    "x_bbs_assemble_control":         "BBSAction",
    "x_calendar_assemble_control":    "CalendarAction",
    "x_cms_assemble_control":         "CMSBlockAction",
    "x_collaboration_assemble_websocket": "WebSocketAction",
    "x_component_assemble_control":   "ComponentAction",
    "x_faceset_control":              "FaceSetAction",
    "x_file_assemble_control":        "FileAction",
    "x_general_assemble_control":     "GeneralAction",
    "x_hotpic_assemble_control":      "HotPicAction",
    "x_meeting_assemble_control":     "MeetingAction",
    "x_message_assemble_communicate": "MessageCommunicateAction",
    "x_mind_assemble_control":        "MindAction",
    "x_okr_assemble_control":         "OKRAction",
    "x_organization_assemble_authentication": "AuthAction",
    "x_organization_assemble_control":  "OrganizationAction",
    "x_organization_assemble_express":  "OrganizationExpressAction",
    "x_organization_assemble_personal": "PersonalAction",
    "x_portal_assemble_designer":     "PortalDesignerAction",
    "x_portal_assemble_surface":      "PortalSurfaceAction",
    "x_processplatform_assemble_bam":   "BAMAction",
    "x_processplatform_assemble_designer": "DesignerAction",
    "x_processplatform_assemble_surface": "ProcessPlatformSurfaceAction",
    "x_program_center":               "ProgramCenterAction",
    "x_query_assemble_designer":      "QueryDesignerAction",
    "x_query_assemble_surface":       "QuerySurfaceAction",
    "x_smartoffice_control":          "SmartOfficeControl",
    "x_strategydeploy_assemble_control":"StrategyDeployAction",
    "x_teamwork_assemble_control":    "TeamworkAction",
}


def strip_comments(text: str) -> str:
    """Remove /* */ block comments and // line comments from JSON-like text."""
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
    lines = text.splitlines()
    out_lines = []
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("//"):
            continue
        idx = stripped.find("//")
        while idx != -1:
            before = stripped[:idx]
            qcount = before.count('"')
            if qcount % 2 == 0:
                stripped = stripped[:idx]
                break
            else:
                idx = stripped.find("//", idx + 2)
        out_lines.append(stripped)
    return "\n".join(out_lines)


def process_service_file(filepath):
    """Read a single service JSON file, strip comments, parse as JSON, build doc content."""
    raw = open(filepath, "r", encoding="utf-8").read()
    cleaned = strip_comments(raw)
    
    # Try to parse; if there are control characters or other issues, skip
    try:
        data = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        return None
    
    # Determine the action name from the module filename
    fname = os.path.splitext(os.path.basename(filepath))[0]
    action_name = MODULE_TO_ACTION.get(fname)
    if not action_name:
        # Fallback: derive from filename
        parts = fname.replace("x_", "").replace("_assemble_control", "Action").replace("_assemble_surface", "SurfaceAction").replace("_assemble_designer", "DesignerAction").title()
        # Simple capitalization fix
        action_name = re.sub(r'([a-z])([A-Z])', r'\1 \2', parts) if False else parts
    
    # data is a dict: {op_name: {"uri": "...", "method": "POST"}, ...}
    lines = []
    for op_name, op_info in data.items():
        if not isinstance(op_info, dict):
            continue
        uri = op_info.get("uri", "")
        method = op_info.get("method", "GET")
        lines.append(f"  - {op_name}: {method} {uri}")
    
    module_display = fname.replace("x_", "").replace("_", " ").title()
    content = f"O2OA API 模块: {module_display}\n\n操作列表:\n" + "\n".join(lines)
    doc_id = f"o2kb::o2oa_api::{action_name}"
    title = f"O2OA API - {action_name}"
    return doc_id, title, content


def ingest_doc(doc_id, title, category, content, creator_person="AI助手"):
    """POST a doc to /idx-gateway-doc/update with auth token."""
    url = "http://127.0.0.1:18790/gateway/idx-gateway-doc/update"
    headers = {"Authorization": TOKEN, "Content-Type": "application/json"}
    payload = {
        "id": doc_id,
        "title": title,
        "category": category,
        "content": content,
        "creatorPerson": creator_person,
        "creatorUnit": "",
        "questionEnable": True,
        "permissionList": [],
        "meta": json.dumps({"topic": "o2oa_api_services", "source": "services_json"}, ensure_ascii=False),
    }
    resp = httpx.post(url, headers=headers, json=payload, timeout=30)
    return resp


def main():
    json_files = sorted([
        os.path.join(BASE, f) 
        for f in os.listdir(BASE) 
        if f.endswith(".json")
    ])
    print(f"Found {len(json_files)} service JSON files in {BASE}")
    
    success = 0
    skipped = 0
    
    for i, fpath in enumerate(json_files, 1):
        result = process_service_file(fpath)
        if result is None:
            print(f"  [SKIP] {os.path.basename(fpath)}: parse error or unsupported module")
            skipped += 1
            continue
        
        doc_id, title, content = result
        
        resp = ingest_doc(doc_id, title, CATEGORY, content)
        if resp.status_code in (200, 201):
            print(f"  [OK] {title} ({doc_id})")
            success += 1
        else:
            print(f"  [WARN] ingest failed for {title}: status {resp.status_code}, body: {resp.text[:200]}")
            skipped += 1
    
    print(f"\nDone: {success} succeeded, {skipped} skipped out of {len(json_files)} files.")
    

if __name__ == "__main__":
    main()
