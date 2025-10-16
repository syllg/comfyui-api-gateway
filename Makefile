run: 
	python -m src.app.api.api --reload

gradio:
	python src\app\app.py
	
install:
	pip install -r requirements.txt

test-ngrok:
	python src\app\test\test_ngrok_compatibility.py

test_url:
	python src\app\test\test_url_fix.py 