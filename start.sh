#!/bin/bash

echo "Executando script de inicialização do banco de dados (init_db.py)..."
python init_db.py

echo "Iniciando a aplicação Flask (app.py)..."
exec python app.py