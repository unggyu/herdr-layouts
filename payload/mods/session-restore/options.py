def build_argv(record):
    options=[]
    source=iter(record.get('options', []))
    for value in source:
        if value in ('--yolo','--dangerously-bypass-approvals-and-sandbox','--full-auto','--approve-for-me'): continue
        if value in ('-a','--ask-for-approval','-s','--sandbox'):
            next(source,None);continue
        if any(value.startswith(k+'=') for k in ('--ask-for-approval','--sandbox','-a','-s')): continue
        options.append(value)
    result = [record['codex'], '--yolo', *options]
    if record.get("session_id"):
        result.extend(["resume", record["session_id"]])
    elif record.get("evidence") == "resume-picker":
        result.append("resume")
    elif record.get("evidence") == "fresh-cli":
        pass
    else:
        raise ValueError("No verified Codex conversation is saved")
    return result
