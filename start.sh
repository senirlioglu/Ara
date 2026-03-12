#!/bin/bash
PORT="${PORT:-8501}"

# Deploy sırasında öneri listesini güncelle (fiyat bilgisi dahil)
echo "Pipeline çalıştırılıyor..."
python urun_master_pipeline.py && echo "Pipeline OK" || echo "Pipeline atlandı (hata oluştu)"

exec streamlit run urun_ara_app.py \
    --server.port="$PORT" \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --server.enableCORS=false \
    --server.enableXsrfProtection=false
