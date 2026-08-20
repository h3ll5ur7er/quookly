# My Fullstack Template CLI

## generate openapi client

```bash
cd cli
uv run my_fullstack_template_cli codegen openapi generate --url http://localhost:8000/openapi.json --output-path src/my_fullstack_template_cli/api_client/ --meta none --overwrite 
```
