//= require ./all_nosearch
//= require ./app/_search

function copyText(x, str) {

  // Create an element with the text, copy it, then remove it
  const el = document.createElement('textarea');
  el.value = str;
  document.body.appendChild(el);
  el.select();
  document.execCommand('copy');
  document.body.removeChild(el);

  // Change the text in the button to note it's been copied
  x.innerHTML = "  ✓  ";
}
