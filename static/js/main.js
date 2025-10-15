document.addEventListener('DOMContentLoaded', () => {
  initBarcodeScanner();
  initWineCards();
  initWineActions();
});

function initBarcodeScanner() {
  const scanBtn = document.getElementById('scan-btn');
  const scannerContainer = document.getElementById('scanner-container');
  const barcodeInput = document.getElementById('barcode');
  const scannerTarget = document.getElementById('scanner');

  if (!scanBtn || !window.Quagga) {
    return;
  }

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

function initWineCards() {
  const cards = document.querySelectorAll('.wine-card');
  if (!cards.length || typeof bootstrap === 'undefined') {
    return;
  }

  cards.forEach((card) => {
    let content = "Les informations enrichies arrivent…";
    try {
      const rawPreview = card.dataset.winePreview;
      if (rawPreview) {
        const preview = JSON.parse(rawPreview);
        if (Array.isArray(preview) && preview.length) {
          content = preview
            .map((item) => {
              const title = item.title ? `<strong>${item.title}</strong>` : '';
              const source = item.source ? `<span class="text-muted"> (${item.source})</span>` : '';
              return `<div class="mb-2">${title}${source}<div>${escapeHtml(item.content)}</div></div>`;
            })
            .join('');
        }
      }
    } catch (err) {
      console.warn('Impossible de parser les informations enrichies', err);
    }

    const popover = new bootstrap.Popover(card, {
      trigger: 'hover focus',
      placement: 'auto',
      html: true,
      title: card.querySelector('.card-title')?.textContent || 'Informations',
      content,
    });

    card.addEventListener('click', (event) => {
      if (event.target.closest('.wine-action-form')) {
        return;
      }
      const url = card.dataset.detailUrl;
      if (url) {
        event.preventDefault();
        popover.hide();
        window.location.href = url;
      }
    });
  });
}

function initWineActions() {
  document.querySelectorAll('.wine-action-form[data-confirm]').forEach((form) => {
    form.addEventListener('submit', (event) => {
      const message = form.getAttribute('data-confirm');
      if (message && !window.confirm(message)) {
        event.preventDefault();
      }
    });
  });
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text || '';
  return div.innerHTML.replace(/\n/g, '<br>');
}
