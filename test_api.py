import requests
import json

def test_api():
    """AI Brain API'sini test eder"""
    
    print("AI Brain API Test başlatılıyor...")
    
    # Test URL
    base_url = "http://localhost:8080"
    
    # Soru sorma testi
    print("\n1. Soru Sorma Testi:")
    ask_url = f"{base_url}/ai-brain/api/ask"
    question_data = {
        "question": "Stoktaki ürünleri listele"
    }
    
    try:
        response = requests.post(ask_url, json=question_data)
        print(f"Durum Kodu: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("Yanıt:", json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print("Hata:", response.text)
    except Exception as e:
        print(f"İstek hatası: {str(e)}")
    
    # Analiz testi
    print("\n2. Analiz Testi:")
    analyze_url = f"{base_url}/ai-brain/api/analyze"
    analyze_data = {
        "analysis_type": "daily"
    }
    
    try:
        response = requests.post(analyze_url, json=analyze_data)
        print(f"Durum Kodu: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            if result.get("success"):
                print("Analiz başarılı!")
                print("Analiz Özeti:", result.get("analysis")[:200] + "..." if result.get("analysis") else "Analiz sonucu yok")
            else:
                print("Hata:", result.get("error"))
        else:
            print("Hata:", response.text)
    except Exception as e:
        print(f"İstek hatası: {str(e)}")
    
    print("\nTest tamamlandı.")

if __name__ == "__main__":
    test_api()