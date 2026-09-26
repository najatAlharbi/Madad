(() => {
  const SIGNED_IN_HOSPITAL_ID = 638;
  const root = document.getElementById('madad-interfaces');
  const dataset = window.MADAD_INTERFACE_DATA;
  const navigation = Array.from(root.querySelectorAll('[data-warehouse-view]'));
  const panels = Array.from(root.querySelectorAll('[data-warehouse-panel]'));
  const transfers = [];
  let currentHospital = null;
  let lastMatches = [];

  const formatNumber = (value) => new Intl.NumberFormat('en-US').format(Number(value || 0));
  const formatDate = (value) => {
    if (!value) return 'Not available';
    return new Intl.DateTimeFormat('en', { day: '2-digit', month: 'short', year: 'numeric' })
      .format(new Date(`${value}T00:00:00`));
  };

  const createStatus = (label, statusCode = 'info') => {
    const badge = document.createElement('span');
    badge.className = `madad-status status-${statusCode}`;
    badge.textContent = label;
    return badge;
  };

  const renderEmptyRow = (body, columnCount, title, message) => {
    const row = document.createElement('tr');
    const cell = document.createElement('td');
    cell.colSpan = columnCount;
    const empty = document.createElement('div');
    empty.className = 'madad-empty-state';
    const heading = document.createElement('strong');
    heading.textContent = title;
    const note = document.createElement('span');
    note.textContent = message;
    empty.append(heading, note);
    cell.appendChild(empty);
    row.appendChild(cell);
    body.replaceChildren(row);
  };

  const renderInventory = () => {
    const body = root.querySelector('#madad-inventory-body');
    const query = root.querySelector('#madad-inventory-search').value.trim().toLowerCase();
    const status = root.querySelector('#madad-inventory-status').value;
    const records = currentHospital.inventory.filter((item) => {
      const matchesQuery = !query || item.name.toLowerCase().includes(query);
      const matchesStatus = !status || item.statusCode === status;
      return matchesQuery && matchesStatus;
    });

    body.replaceChildren();
    if (!records.length) {
      renderEmptyRow(body, 6, 'No matching inventory records', 'Change the search or status filter.');
      return;
    }

    records.forEach((item) => {
      const row = document.createElement('tr');
      const values = [
        item.name,
        formatNumber(item.availableQuantity),
        formatNumber(item.lastConsumption),
        formatNumber(item.lastReceived),
        formatDate(item.recordDate)
      ];
      values.forEach((value, index) => {
        const cell = document.createElement('td');
        cell.textContent = value;
        if ([1, 2, 3].includes(index)) cell.classList.add('madad-number');
        row.appendChild(cell);
      });
      const statusCell = document.createElement('td');
      statusCell.appendChild(createStatus(item.status, item.statusCode));
      row.appendChild(statusCell);
      body.appendChild(row);
    });

    root.querySelector('#madad-warehouse-feedback').textContent =
      `My Inventory: showing ${formatNumber(records.length)} records for ${currentHospital.label}.`;
  };

  const renderNeedSignals = () => {
    const body = root.querySelector('#madad-warehouse-needs-body');
    const records = currentHospital.inventory.filter((item) => item.statusCode !== 'good');
    body.replaceChildren();

    if (!records.length) {
      renderEmptyRow(body, 4, 'No need signals', 'The latest records contain no stockout flag or zero closing balance.');
      return;
    }

    records.slice(0, 12).forEach((item) => {
      const row = document.createElement('tr');
      const name = document.createElement('td');
      name.textContent = item.name;
      const quantity = document.createElement('td');
      quantity.className = 'madad-number';
      quantity.textContent = formatNumber(item.availableQuantity);
      const status = document.createElement('td');
      status.appendChild(createStatus(item.status, item.statusCode));
      const date = document.createElement('td');
      date.textContent = formatDate(item.recordDate);
      row.append(name, quantity, status, date);
      body.appendChild(row);
    });
  };

  const addScopeFact = (label, value, detail, statusCode) => {
    const container = root.querySelector('#madad-warehouse-scope');
    const card = document.createElement('div');
    card.className = 'madad-risk-item';
    const head = document.createElement('div');
    head.className = 'madad-risk-row';
    const title = document.createElement('span');
    title.textContent = label;
    head.append(title, createStatus(value, statusCode));
    const note = document.createElement('div');
    note.className = 'madad-context-note';
    note.textContent = detail;
    card.append(head, note);
    container.appendChild(card);
  };

  const renderScope = () => {
    const container = root.querySelector('#madad-warehouse-scope');
    container.replaceChildren();
    addScopeFact('Role access', 'Restricted', `${currentHospital.label} only; other hospitals appear only in emergency matching.`, 'good');
    addScopeFact('Inventory update', formatDate(currentHospital.historyEnd), 'Latest product-level records for this hospital.', 'info');
    addScopeFact('Batch and expiry', 'Pending', 'Batch and expiry details will appear when the inventory service provides them.', 'warn');
    addScopeFact(
      'Forecasted needs',
      'Coming soon',
      'Expected shortages and recommended quantities will appear when the forecasting service is connected.',
      'warn'
    );
  };

  const renderTransfers = () => {
    const body = root.querySelector('#madad-transfer-body');
    body.replaceChildren();

    if (!transfers.length) {
      renderEmptyRow(
        body,
        5,
        'No transfer requests in this session',
        'Use Emergency Matching and choose a supplying hospital.'
      );
      return;
    }

    transfers.forEach((transfer) => {
      const row = document.createElement('tr');
      const values = [
        transfer.supplier,
        transfer.supply,
        formatNumber(transfer.quantity),
        transfer.urgency
      ];
      values.forEach((value, index) => {
        const cell = document.createElement('td');
        cell.textContent = value;
        if (index === 2) cell.classList.add('madad-number');
        row.appendChild(cell);
      });
      const status = document.createElement('td');
      status.appendChild(createStatus('Pending coordination', 'warn'));
      row.appendChild(status);
      body.appendChild(row);
    });
  };

  const createTransfer = (supplierId) => {
    const supplier = dataset.hospitals.find((hospital) => hospital.id === supplierId);
    const selectedProduct = dataset.products.find(
      (product) => String(product.id) === root.querySelector('#madad-supply-select').value
    );
    const quantity = Number(root.querySelector('#madad-request-qty').value);
    const urgency = root.querySelector('#madad-priority').value;
    if (!supplier || !selectedProduct || !quantity) return;

    transfers.push({
      supplier: supplier.label,
      supply: selectedProduct.name,
      quantity,
      urgency
    });
    root.querySelector('#madad-warehouse-feedback').textContent =
      `Transfer request prepared for ${formatNumber(quantity)} units from ${supplier.label}. Contact details and submission require the production backend.`;
    renderSupplierMatches(lastMatches, true);
  };

  const renderSupplierMatches = (matches, requestCreated = false) => {
    const results = root.querySelector('#madad-supplier-results');
    results.replaceChildren();

    if (!matches.length) {
      const empty = document.createElement('div');
      empty.className = 'madad-empty-state';
      const title = document.createElement('strong');
      title.textContent = 'No hospital has the requested quantity';
      const note = document.createElement('span');
      note.textContent = 'Try a lower quantity or another medical supply.';
      empty.append(title, note);
      results.appendChild(empty);
      return;
    }

    matches.forEach((match) => {
      const card = document.createElement('article');
      card.className = 'madad-supplier';
      const head = document.createElement('div');
      head.className = 'madad-supplier-head';
      const name = document.createElement('div');
      name.className = 'madad-supplier-name';
      name.textContent = match.hospital.label;
      head.append(name, createStatus(`${formatNumber(match.item.availableQuantity)} available`, 'good'));

      const meta = document.createElement('div');
      meta.className = 'madad-supplier-meta';
      const distance = document.createElement('span');
      distance.textContent = `${match.distanceKm.toFixed(1)} km away`;
      const district = document.createElement('span');
      district.textContent = match.hospital.district;
      const date = document.createElement('span');
      date.textContent = `Record: ${formatDate(match.item.recordDate)}`;
      meta.append(distance, district, date);

      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'madad-secondary-button madad-supplier-action';
      button.textContent = requestCreated ? 'Prepare another request' : 'Prepare transfer request';
      button.addEventListener('click', () => createTransfer(match.hospital.id));
      card.append(head, meta, button);
      results.appendChild(card);
    });
  };

  const findSuppliers = () => {
    const productId = Number(root.querySelector('#madad-supply-select').value);
    const quantity = Number(root.querySelector('#madad-request-qty').value);

    if (!productId) {
      renderSupplierMatches([]);
      root.querySelector('#madad-supplier-results strong').textContent = 'Select a medical supply';
      root.querySelector('#madad-supplier-results span').textContent =
        'Choose the required medical supply before searching nearby hospitals.';
      root.querySelector('#madad-warehouse-feedback').textContent = 'Select a medical supply first.';
      return;
    }
    if (!Number.isInteger(quantity) || quantity < 1) {
      renderSupplierMatches([]);
      root.querySelector('#madad-supplier-results strong').textContent = 'Enter a valid quantity';
      root.querySelector('#madad-supplier-results span').textContent =
        'Required quantity must be a whole number of at least 1.';
      root.querySelector('#madad-warehouse-feedback').textContent = 'Enter a whole required quantity of at least 1.';
      return;
    }

    lastMatches = dataset.hospitals
      .filter((hospital) => hospital.id !== currentHospital.id)
      .map((hospital) => ({
        hospital,
        item: hospital.inventory.find((item) => item.productId === productId),
        distanceKm: Number(currentHospital.distancesKm[String(hospital.id)])
      }))
      .filter((match) =>
        match.item &&
        match.item.statusCode === 'good' &&
        Number(match.item.availableQuantity) >= quantity &&
        Number.isFinite(match.distanceKm)
      )
      .sort((a, b) => a.distanceKm - b.distanceKm);

    renderSupplierMatches(lastMatches);
    root.querySelector('#madad-warehouse-feedback').textContent = lastMatches.length
      ? `Found ${lastMatches.length} hospital warehouse${lastMatches.length === 1 ? '' : 's'} with at least ${formatNumber(quantity)} units, ordered by distance.`
      : `No other hospital warehouse currently has at least ${formatNumber(quantity)} units of the selected supply.`;
  };

  const views = {
    overview: {
      title: 'My Hospital Warehouse',
      description: 'Operational access to the signed-in hospital warehouse only.'
    },
    inventory: {
      title: 'My Inventory',
      description: 'Latest medical supply records for the signed-in hospital.'
    },
    emergency: {
      title: 'Emergency Matching',
      description: 'Find the nearest hospital warehouse with enough available stock.'
    },
    transfers: {
      title: 'Transfers',
      description: 'Review transfer requests created during this browser session.'
    },
    forecasts: {
      title: 'Forecasted Needs',
      description: 'Review expected medical supply requirements for this hospital.'
    }
  };

  const openView = (viewName) => {
    const view = views[viewName] || views.overview;
    const selected = views[viewName] ? viewName : 'overview';
    navigation.forEach((button) => {
      button.classList.toggle('is-active', button.dataset.warehouseView === selected);
    });
    panels.forEach((panel) => {
      panel.hidden = panel.dataset.warehousePanel !== selected;
    });
    root.querySelector('#madad-warehouse-title').textContent = view.title;

    if (selected === 'overview') {
      root.querySelector('#madad-warehouse-feedback').textContent =
        `${currentHospital.label} overview updated through ${formatDate(currentHospital.historyEnd)}.`;
    } else if (selected === 'inventory') {
      renderInventory();
    } else if (selected === 'emergency') {
      root.querySelector('#madad-warehouse-feedback').textContent =
        'Complete the emergency request to search other hospital warehouses.';
    } else if (selected === 'transfers') {
      renderTransfers();
      root.querySelector('#madad-warehouse-feedback').textContent =
        `Transfers: ${transfers.length} request${transfers.length === 1 ? '' : 's'} in this session.`;
    } else {
      root.querySelector('#madad-warehouse-feedback').textContent =
        'Forecast results will appear when the forecasting service is connected.';
    }
  };

  if (!dataset) {
    root.querySelector('#madad-warehouse-data-badge').textContent = 'Interface Ready';
    root.querySelector('#madad-warehouse-feedback').textContent =
      'Connect the hospital inventory service to display warehouse records.';
    return;
  }

  currentHospital =
    dataset.hospitals.find((hospital) => hospital.id === SIGNED_IN_HOSPITAL_ID) ||
    dataset.hospitals[0];

  if (!currentHospital) {
    root.querySelector('#madad-warehouse-feedback').textContent =
      'No hospital warehouse records are currently available.';
    return;
  }

  root.querySelector('#madad-warehouse-role-scope').textContent =
    `${currentHospital.label} · ${currentHospital.warehouseLabel} only`;
  root.querySelector('#madad-warehouse-available').textContent =
    formatNumber(currentHospital.availableProductCount);
  root.querySelector('#madad-warehouse-needs').textContent =
    formatNumber(currentHospital.needSignalCount);
  root.querySelector('#madad-warehouse-total').textContent =
    formatNumber(currentHospital.totalAvailableQuantity);
  root.querySelector('#madad-warehouse-overview-caption').textContent =
    `${currentHospital.label} · records through ${formatDate(currentHospital.historyEnd)}`;
  root.querySelector('#madad-inventory-caption').textContent =
    `${currentHospital.label} · latest record for each product`;

  const supplySelect = root.querySelector('#madad-supply-select');
  dataset.products.forEach((product) => {
    supplySelect.add(new Option(product.name, String(product.id)));
  });

  navigation.forEach((button) => {
    button.addEventListener('click', () => openView(button.dataset.warehouseView));
  });
  root.querySelector('#madad-focus-request').addEventListener('click', () => openView('emergency'));
  root.querySelector('#madad-full-inventory').addEventListener('click', () => openView('inventory'));
  root.querySelector('#madad-find-suppliers').addEventListener('click', findSuppliers);
  root.querySelector('#madad-inventory-search').addEventListener('input', renderInventory);
  root.querySelector('#madad-inventory-status').addEventListener('change', renderInventory);

  renderNeedSignals();
  renderScope();
  openView('overview');
  if (window.lucide) window.lucide.createIcons();
})();
