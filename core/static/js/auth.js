// Show/hide password toggle for the login and register forms.
document.addEventListener('click', function (e) {
    const btn = e.target.closest('.password-toggle');
    if (!btn) return;
    e.preventDefault();

    const input = document.getElementById(btn.dataset.target);
    if (!input) return;

    const willShow = input.type === 'password';
    input.type = willShow ? 'text' : 'password';
    btn.classList.toggle('showing', willShow);
    btn.setAttribute('aria-label', willShow ? 'Hide password' : 'Show password');
});
