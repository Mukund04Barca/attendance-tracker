#!/bin/bash
echo "Building Vercel deployment..."
pip install -r requirements.txt
python manage.py collectstatic --noinput --clear
echo "Build complete."
