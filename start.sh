#!/bin/bash

echo "Executando script de inicialização do banco de dados (init_db.py)..."
poetry run python init_db.py

echo "Iniciando a aplicação Flask (app.py)..."
exec poetry run python app.py