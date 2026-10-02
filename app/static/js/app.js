// Global App Helpers for productos.bona (Agile Lumelí Flow)

function formatMoney(amount) {
  return new Intl.NumberFormat('es-AR', {
    style: 'currency',
    currency: 'ARS',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0
  }).format(amount || 0);
}

function showToast(message, type = 'success') {
  const container = document.getElementById('toastContainer');
  if (!container) return;

  const toast = document.createElement('div');
  const isSuccess = type === 'success';
  const isError = type === 'error';
  const isWarning = type === 'warning';

  let bgClass = 'bg-slate-800 border-slate-700 text-white';
  let icon = '<i class="fa-solid fa-circle-check text-emerald-400"></i>';

  if (isSuccess) {
    bgClass = 'bg-slate-900 border-emerald-500/40 text-emerald-200';
    icon = '<i class="fa-solid fa-circle-check text-emerald-400 text-lg"></i>';
  } else if (isError) {
    bgClass = 'bg-slate-900 border-rose-500/40 text-rose-200';
    icon = '<i class="fa-solid fa-circle-exclamation text-rose-400 text-lg"></i>';
  } else if (isWarning) {
    bgClass = 'bg-slate-900 border-yellow-500/40 text-yellow-200';
    icon = '<i class="fa-solid fa-triangle-exclamation text-yellow-400 text-lg"></i>';
  }

  toast.className = `pointer-events-auto flex items-center gap-3 px-4 py-3 rounded-xl border shadow-xl backdrop-blur-md transition-all duration-300 transform translate-y-2 opacity-0 text-sm ${bgClass}`;
  toast.innerHTML = `
    ${icon}
    <div class="font-medium">${message}</div>
    <button onclick="this.parentElement.remove()" class="ml-auto text-slate-400 hover:text-white pl-2">
      <i class="fa-solid fa-xmark"></i>
    </button>
  `;

  container.appendChild(toast);

  // Trigger animation
  requestAnimationFrame(() => {
    toast.classList.remove('translate-y-2', 'opacity-0');
  });

  // Auto remove
  setTimeout(() => {
    toast.classList.add('opacity-0', '-translate-y-2');
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

function openModal(id) {
  const m = document.getElementById(id);
  if (m) m.classList.remove('hidden');
}

function closeModal(id) {
  const m = document.getElementById(id);
  if (m) m.classList.add('hidden');
}

// Cargar cuentas activas y balance global
async function loadGlobalAccounts() {
  try {
    const res = await fetch('/api/accounts');
    if (!res.ok) return;
    const accounts = await res.json();
    
    // Calcular balance total
    let totalCash = 0;
    const expSelect = document.getElementById('expAccount');
    if (expSelect) {
      expSelect.innerHTML = '';
    }

    accounts.forEach(acc => {
      totalCash += acc.current_balance;
      if (expSelect) {
        const opt = document.createElement('option');
        opt.value = acc.id;
        opt.textContent = `${acc.name} (${formatMoney(acc.current_balance)})`;
        expSelect.appendChild(opt);
      }
    });

    const headerCash = document.getElementById('headerCashTotal');
    if (headerCash) {
      headerCash.textContent = formatMoney(totalCash);
    }
  } catch (err) {
    console.error('Error cargando cuentas:', err);
  }
}

// Registrar gasto rápido
async function handleQuickExpense(e) {
  e.preventDefault();
  const amount = parseFloat(document.getElementById('expAmount').value);
  const category = document.getElementById('expCategory').value;
  const description = document.getElementById('expDesc').value;
  const account_id = parseInt(document.getElementById('expAccount').value);

  if (!amount || amount <= 0) {
    showToast('El monto debe ser mayor a 0', 'warning');
    return;
  }

  try {
    const res = await fetch('/api/expenses', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        amount,
        category,
        description,
        account_id,
        status: 'Pagado'
      })
    });

    if (res.ok) {
      showToast('Gasto registrado e impactado en caja exitosamente 💸', 'success');
      closeModal('quickExpenseModal');
      document.getElementById('quickExpenseForm').reset();
      loadGlobalAccounts();
      // Si estamos en la página de flujo o dashboard, recargar métricas
      if (typeof reloadMetrics === 'function') reloadMetrics();
      if (typeof reloadExpenses === 'function') reloadExpenses();
    } else {
      const err = await res.json();
      showToast(err.detail || 'Error al guardar el gasto', 'error');
    }
  } catch (err) {
    showToast('Error de red al registrar gasto', 'error');
  }
}

// Al cargar el DOM
document.addEventListener('DOMContentLoaded', () => {
  loadGlobalAccounts();
});
