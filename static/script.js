'use strict';
const partnerInputs = [...document.querySelectorAll('input[name="partner"]')];
const partnerInfo = [...document.querySelectorAll('#partner-descriptions span')];
function showPartner(id) {
  const partner = partnerInfo.find(item => item.dataset.partner === id);
  if (!partner) return;
  const input = partnerInputs.find(item => item.value === id);
  input.checked = true;
  document.getElementById('selected-partner').textContent = `選択中：${partner.dataset.name}`;
  document.getElementById('composer-partner-name').textContent = partner.dataset.name;
  try { localStorage.setItem('digilink-partner', id); } catch (_) { /* 保存できない環境でも投稿は可能。 */ }
}

const lightbox = document.getElementById('image-lightbox');
const lightboxImage = lightbox.querySelector('.lightbox-image');
let imageOpener;
for (const link of document.querySelectorAll('.post-image-link')) {
  link.addEventListener('click', event => {
    if (lightbox.open) return;
    event.preventDefault();
    imageOpener = link;
    lightboxImage.src = link.href;
    lightboxImage.alt = link.querySelector('img').alt;
    lightbox.showModal();
  });
}
lightbox.querySelector('.lightbox-close').addEventListener('click', () => lightbox.close());
lightbox.addEventListener('click', event => {
  if (event.target === lightbox) lightbox.close();
});
lightbox.addEventListener('close', () => {
  lightboxImage.removeAttribute('src');
  imageOpener?.focus({ preventScroll: true });
  imageOpener = null;
});
partnerInputs.forEach(input => input.addEventListener('change', () => showPartner(input.value)));
if (!document.getElementById('form-errors')) {
  try { const saved = localStorage.getItem('digilink-partner'); if (saved) showPartner(saved); } catch (_) { /* 選択中の値を使用。 */ }
}
document.getElementById('find-partner')?.addEventListener('click', () => {
  const partner = partnerInfo[Math.floor(Math.random() * partnerInfo.length)];
  showPartner(partner.dataset.partner);
  document.getElementById('random-result').textContent = `${partner.dataset.name}：${partner.textContent}`;
});
const body = document.getElementById('body');
body?.addEventListener('input', () => {
  document.getElementById('body-count').textContent = `${[...body.value].length} / 2,000`;
});
const imageInput = document.getElementById('image');
const preview = document.getElementById('image-preview');
const removeButton = document.getElementById('remove-image');
let previewUrl;
function clearPreview() {
  if (previewUrl) URL.revokeObjectURL(previewUrl);
  previewUrl = undefined;
  preview.hidden = true;
  preview.removeAttribute('src');
  removeButton.hidden = true;
}
imageInput?.addEventListener('change', () => {
  clearPreview();
  const error = document.getElementById('image-error');
  error.textContent = '';
  const file = imageInput.files[0];
  if (!file) return;
  if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type) || file.size > 5 * 1024 * 1024) {
    error.textContent = '5MB以下のJPEG・PNG・WebP画像を選んでください。';
    imageInput.value = '';
    return;
  }
  previewUrl = URL.createObjectURL(file);
  preview.src = previewUrl;
  preview.hidden = false;
  removeButton.hidden = false;
});
removeButton?.addEventListener('click', () => { imageInput.value = ''; clearPreview(); });
document.getElementById('post-form')?.addEventListener('submit', (event) => {
  for (const id of ['title', 'body']) {
    const input = document.getElementById(id);
    if (!input.value.trim()) {
      event.preventDefault();
      input.setCustomValidity('空白だけでは投稿できません。');
      input.reportValidity();
      input.addEventListener('input', () => input.setCustomValidity(''), { once: true });
      return;
    }
  }
  const button = event.target.querySelector('button[type="submit"]');
  button.disabled = true;
  button.textContent = '投稿しています…';
});
window.addEventListener('pageshow', () => {
  const button = document.querySelector('.submit-button');
  if (button) { button.disabled = false; button.textContent = 'このパートナーで投稿する →'; }
});
document.getElementById('form-errors')?.focus();
