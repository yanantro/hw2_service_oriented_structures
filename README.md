# hw2_service_oriented_structures

Запуск
```bash
docker compose up --build
```
API http://localhost:8000

Swagger ui http://localhost:8000/docs

База `docker compose exec db psql -U marketplace -d marketplace`

Кодогенерация
```bash
pip install -r requirements-codegen.txt
./scripts/generate.sh
```
