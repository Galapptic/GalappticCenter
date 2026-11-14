(function(){
  var q = new URLSearchParams(location.search);
  var challenge = q.has('challenge');
  var ref = (q.get('ref') || q.get('utm_source') || '').toLowerCase().replace(/[^a-z0-9_]/g, '').slice(0, 30);
  var ct = challenge ? 'challenge' : (ref || 'web');
  document.querySelectorAll('a[data-store]').forEach(function(a){
    a.href = 'https://apps.apple.com/app/apple-store/id6766752682?pt=128866802&ct=' + ct + '&mt=8';
  });
  if (!challenge || !document.getElementById('ask')) return;
  document.body.classList.add('ask');
  document.querySelectorAll('#ask button').forEach(function(b){
    b.addEventListener('click', function(){
      var right = b.getAttribute('data-guess') === 'true';
      document.getElementById('verdict').textContent = right ? 'You got it: it\u2019s true.' : 'Surprise: it\u2019s true.';
      document.body.classList.remove('ask');
      document.body.classList.add('told');
      window.scrollTo(0, 0);
    });
  });
})();
