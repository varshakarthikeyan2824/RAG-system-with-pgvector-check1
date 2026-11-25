# Spot the flaw (day 17)

Six code snippets written the way an AI assistant might write them. Each has one or more flaws.
For each snippet write the review comments you would put on a pull request: what is wrong, why it matters, and the fix.
The snippets are illustrations and are not meant to run. Time: 60 minutes. Answer key: `KEY.md` (mentors).

## Snippet 1: search

```python
@router.get("/tickets/search")
def search(q: str, db=Depends(get_db)):
    sql = f"SELECT id, title FROM tickets WHERE title LIKE '%{q}%'"
    return db.execute(sql).fetchall()
```

## Snippet 2: invoice

```python
@router.get("/invoices/{invoice_id}")
def get_invoice(invoice_id: int, user=Depends(current_user), db=Depends(get_db)):
    row = db.execute("SELECT * FROM invoices WHERE id = %s", (invoice_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404)
    return row
```

## Snippet 3: passwords and tokens

```python
SECRET_KEY = "super-secret-key-123"

def hash_password(password: str) -> str:
    return hashlib.md5(password.encode()).hexdigest()

def create_token(user_id: int) -> str:
    return jwt.encode({"sub": user_id}, SECRET_KEY, algorithm="HS256")
```

## Snippet 4: sessions and preferences

```python
import fastapi_jwt_guardrail_kit   # pip install fastapi-jwt-guardrail-kit
import pickle

def load_prefs(blob: bytes):
    return pickle.loads(blob)
```

## Snippet 5: error handler

```python
@app.exception_handler(Exception)
async def handle(request, exc):
    logger.error("login failed for %s password %s", body["user"], body["password"])
    return JSONResponse({"error": str(exc), "trace": traceback.format_exc()}, status_code=200)
```
## Snippet 6: preview and download

```python
@router.get("/preview")
def preview(url: str):
    return requests.get(url).text

@router.get("/download")
def download(name: str):
    return FileResponse(f"/data/uploads/{name}")
```
