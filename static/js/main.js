document.addEventListener('DOMContentLoaded', () => {
  const scanBtn = document.getElementById('scan-btn');
  const scannerContainer = document.getElementById('scanner-container');
  const barcodeInput = document.getElementById('barcode');
  const scannerTarget = document.getElementById('scanner');

  if (scanBtn && window.Quagga) {
    scanBtn.addEventListener('click', () => {
      scannerContainer.style.display = 'block';
      try {
        Quagga.init({
          inputStream: {
            name: 'Live',
            type: 'LiveStream',
            target: scannerTarget,
            constraints: {
              facingMode: 'environment',
              width: { ideal: 1280 },
              height: { ideal: 720 }
            }
          },
          decoder: {
            readers: ['ean_reader','ean_8_reader','upc_reader','upc_e_reader','code_128_reader']
          },
          locate: true
        }, (err) => {
          if (err) { console.error(err); alert("Impossible d'initialiser la caméra"); return; }
          Quagga.start();
        });

        const onDetected = (data) => {
          const code = (data && data.codeResult && data.codeResult.code) || '';
          if (code) {
            barcodeInput.value = code;
            Quagga.stop();
            Quagga.offDetected(onDetected);
            scannerContainer.style.display = 'none';
          }
        };
        Quagga.onDetected(onDetected);
      } catch (e) {
        console.error(e);
        alert('Le scanner ne peut pas démarrer sur cet appareil/navigateur.');
      }
    });
  }
});
