#!/bin/bash
set -e

echo "=== Setting up MIKHERB AI Environment ==="

python3 -m pip install -r requirements.txt

cd frontend
npm install
npm run build
cd ..

echo "=== MIKHERB AI Setup Complete ==="
