(() => {
  const root = document.getElementById('madad-interfaces');
  const dataset = window.MADAD_INTERFACE_DATA;
  const navigation = Array.from(root.querySelectorAll('[data-authority-view]'));
  const searchInput = root.querySelector('#madad-authority-search');
  const districtSelect = root.querySelector('#madad-authority-district');
  const tableHead = root.querySelector('#madad-authority-table-head');
  const tableBody = root.querySelector('#madad-authority-table-body');
  const contextBox = root.querySelector('#madad-authority-context');
  const viewAllButton = root.querySelector('#madad-authority-view-all');
  let currentView = 'overview';

  const formatNumber = (value) => new Intl.NumberFormat('en-US').format(Number(value || 0));
  const formatPeriod = (value) => {
    if (!value) return 'Not available';
    return new Intl.DateTimeFormat('en', { month: 'short', year: 'numeric' })
      .format(new Date(`${value}T00:00:00`));
  };

  const createCell = (value, options = {}) => {
    const cell = document.createElement('td');
    if (options.number) cell.classList.add('madad-number');

    if (options.status) {
      const badge = document.createElement('span');
      badge.className = `madad-status status-${options.statusCode || 'info'}`;
      badge.textContent = value;
      cell.appendChild(badge);
    } else {
      cell.textContent = value;
    }
    return cell;
  };

  const views = {
    overview: {
      title: 'Hospital Warehouse Oversight',
      description: 'Central monitoring of hospital-owned warehouses.',
      sectionTitle: 'Current inventory signals',
      sectionCaption: 'Stockout and zero-closing-balance signals across connected hospitals',
      emptyTitle: 'No current inventory signals',
      emptyMessage: 'No hospital-level shortage signal is currently available.',
      columns: [
        { label: 'Hospital', key: 'hospital' },
        { label: 'District', key: 'district' },
        { label: 'Medical supply', key: 'name' },
        { label: 'Status', key: 'status', status: true },
        { label: 'Available', key: 'availableQuantity', number: true }
      ],
      rows: () => dataset.authority.shortageSignals
    },
    hospitals: {
      title: 'Hospitals',
      description: 'View hospitals connected to the medical logistics network.',
      sectionTitle: 'Hospital directory coverage',
      sectionCaption: 'Review connected hospitals and their warehouse status',
      emptyTitle: 'No hospitals found',
      emptyMessage: 'No hospital records are currently available.',
      columns: [
        { label: 'Hospital', key: 'label' },
        { label: 'District', key: 'district' },
        { label: 'Available supplies', key: 'availableProductCount', number: true },
        { label: 'Need signals', key: 'needSignalCount', number: true },
        { label: 'Records through', key: 'historyEnd', period: true }
      ],
      rows: () => dataset.authority.hospitalSummary
    },
    warehouses: {
      title: 'Hospital Warehouses',
      description: 'Read-only monitoring of connected hospital warehouses.',
      sectionTitle: 'Connected hospital warehouses',
      sectionCaption: 'Latest inventory overview by hospital',
      emptyTitle: 'No hospital warehouses found',
      emptyMessage: 'No hospital warehouse records are currently available.',
      columns: [
        { label: 'Hospital', key: 'label' },
        { label: 'Warehouse', key: 'warehouseLabel' },
        { label: 'District', key: 'district' },
        { label: 'Total available', key: 'totalAvailableQuantity', number: true },
        { label: 'Need signals', key: 'needSignalCount', number: true }
      ],
      rows: () => dataset.authority.hospitalSummary
    },
    shortages: {
      title: 'Cross-Hospital Shortages',
      description: 'Monitor stockout flags and zero closing balances across hospital warehouses.',
      sectionTitle: 'Hospital shortage signals',
      sectionCaption: 'Signals use reported stockout status and closing balance',
      emptyTitle: 'No shortage signals',
      emptyMessage: 'No stockout or zero-closing-balance records were found.',
      columns: [
        { label: 'Hospital', key: 'hospital' },
        { label: 'District', key: 'district' },
        { label: 'Medical supply', key: 'name' },
        { label: 'Status', key: 'status', status: true },
        { label: 'Record date', key: 'recordDate', period: true }
      ],
      rows: () => dataset.authority.shortageSignals
    },
    surplus: {
      title: 'Surplus and Expiry',
      description: 'Review available stock, surplus candidates and expiry information.',
      sectionTitle: 'Available stock candidates',
      sectionCaption: 'Positive closing balance is not classified as surplus until a business threshold is approved',
      emptyTitle: 'No available stock candidates',
      emptyMessage: 'No positive hospital closing balances were found.',
      columns: [
        { label: 'Hospital', key: 'hospital' },
        { label: 'District', key: 'district' },
        { label: 'Medical supply', key: 'name' },
        { label: 'Available', key: 'availableQuantity', number: true },
        { label: 'Record date', key: 'recordDate', period: true }
      ],
      rows: () => dataset.authority.availableStockCandidates
    },
    forecasts: {
      title: 'Demand Forecasts',
      description: 'Review anticipated medical supply needs.',
      sectionTitle: 'Forecasted hospital needs',
      sectionCaption: 'Forecast results will appear when the forecasting service is connected',
      emptyTitle: 'Forecast results are not available yet',
      emptyMessage: 'Expected shortages and supply requirements will appear in this section.',
      columns: [
        { label: 'Hospital', key: 'hospital' },
        { label: 'Medical supply', key: 'name' },
        { label: 'Forecast period', key: 'period' },
        { label: 'Predicted need', key: 'predictedNeed', number: true },
        { label: 'Status', key: 'status' }
      ],
      rows: () => []
    }
  };

  const addContextFact = (label, value, detail, statusCode = 'info') => {
    const card = document.createElement('div');
    card.className = 'madad-risk-item';

    const row = document.createElement('div');
    row.className = 'madad-risk-row';
    const name = document.createElement('span');
    name.textContent = label;
    const badge = document.createElement('span');
    badge.className = `madad-status status-${statusCode}`;
    badge.textContent = value;
    row.append(name, badge);

    const note = document.createElement('div');
    note.className = 'madad-context-note';
    note.textContent = detail;
    card.append(row, note);
    contextBox.appendChild(card);
  };

  const renderContext = () => {
    const meta = dataset.meta;
    contextBox.replaceChildren();

    if (currentView === 'surplus') {
      addContextFact('Available stock', 'Supported', 'Current available quantities can be reviewed.', 'good');
      addContextFact('Surplus classification', 'Needs rule', 'A surplus threshold must be approved before automatic classification.', 'warn');
      addContextFact('Batch and expiry', 'Pending', 'Batch and expiry tracking will appear when the inventory service provides it.', 'warn');
      return;
    }

    if (currentView === 'forecasts') {
      addContextFact('Inventory history', 'Available', `${formatNumber(meta.integratedRows)} monthly inventory records can support future forecasting.`, 'good');
      addContextFact('Forecasted needs', 'Coming soon', 'Expected shortages and recommended quantities will appear when the forecasting service is connected.', 'warn');
      addContextFact('Authority access', 'Read only', 'Forecast results will be available for monitoring and allocation decisions.', 'info');
      return;
    }

    addContextFact('Connected hospitals', formatNumber(meta.hospitalWarehousesInInventory), 'Hospital warehouses available for centralized monitoring.', 'good');
    addContextFact('Medical supplies', formatNumber(meta.products), 'Supply items monitored across connected hospitals.', 'good');
    addContextFact('Inventory history', formatPeriod(meta.historyEnd), 'Latest available monitoring period.', 'info');
    addContextFact('Monitoring access', 'Read only', 'The authority can review hospital warehouses without modifying their inventory.', 'info');
  };

  const getFilteredRows = () => {
    const view = views[currentView];
    const query = searchInput.value.trim().toLowerCase();
    const district = districtSelect.value;

    return view.rows().filter((row) => {
      const rowDistrict = row.district || '';
      const matchesDistrict = !district || rowDistrict === district;
      const haystack = Object.values(row).join(' ').toLowerCase();
      return matchesDistrict && (!query || haystack.includes(query));
    });
  };

  const renderDistrictOptions = () => {
    const previous = districtSelect.value;
    const districts = [...new Set(views[currentView].rows().map((row) => row.district).filter(Boolean))].sort();
    districtSelect.replaceChildren(new Option('All districts', ''));
    districts.forEach((district) => districtSelect.add(new Option(district, district)));
    if (districts.includes(previous)) districtSelect.value = previous;
  };

  const renderTable = () => {
    const view = views[currentView];
    const rows = getFilteredRows().slice(0, 60);
    const headerRow = document.createElement('tr');
    view.columns.forEach((column) => {
      const header = document.createElement('th');
      header.textContent = column.label;
      if (column.number) header.classList.add('madad-number');
      headerRow.appendChild(header);
    });
    tableHead.replaceChildren(headerRow);
    tableBody.replaceChildren();

    if (!rows.length) {
      const row = document.createElement('tr');
      const cell = document.createElement('td');
      cell.colSpan = view.columns.length;
      const empty = document.createElement('div');
      empty.className = 'madad-empty-state';
      const title = document.createElement('strong');
      title.textContent = view.emptyTitle;
      const message = document.createElement('span');
      message.textContent = view.emptyMessage;
      empty.append(title, message);
      cell.appendChild(empty);
      row.appendChild(cell);
      tableBody.appendChild(row);
    } else {
      rows.forEach((dataRow) => {
        const row = document.createElement('tr');
        view.columns.forEach((column) => {
          let value = dataRow[column.key];
          if (column.number) value = formatNumber(value);
          if (column.period) value = formatPeriod(value);
          row.appendChild(createCell(value ?? '—', {
            number: column.number,
            status: column.status,
            statusCode: dataRow.statusCode
          }));
        });
        tableBody.appendChild(row);
      });
    }

    root.querySelector('#madad-authority-feedback').textContent =
      `${view.title}: showing ${formatNumber(rows.length)} record${rows.length === 1 ? '' : 's'}.`;
  };

  const setActiveNavigation = () => {
    navigation.forEach((button) => {
      button.classList.toggle('is-active', button.dataset.authorityView === currentView);
    });
  };

  const openView = (viewName) => {
    currentView = views[viewName] ? viewName : 'overview';
    const view = views[currentView];
    setActiveNavigation();
    root.querySelector('#madad-authority-title').textContent = view.title;
    root.querySelector('#madad-authority-section-title').textContent = view.sectionTitle;
    root.querySelector('#madad-authority-section-caption').textContent = view.sectionCaption;
    viewAllButton.textContent = currentView === 'warehouses' ? 'View shortages' : 'View warehouses';
    searchInput.value = '';
    districtSelect.value = '';
    renderDistrictOptions();
    renderContext();
    renderTable();
  };

  if (!dataset) {
    root.querySelector('#madad-authority-data-badge').textContent = 'Interface Ready';
    root.querySelector('#madad-authority-feedback').textContent =
      'Connect the inventory service to display hospital warehouse records.';
    return;
  }

  const meta = dataset.meta;
  root.querySelector('#madad-authority-hospitals').textContent = formatNumber(meta.hospitalWarehousesInInventory);
  root.querySelector('#madad-authority-hospitals-note').textContent =
    `${formatNumber(meta.registeredHospitals)} hospitals are registered in the network`;
  root.querySelector('#madad-authority-products').textContent = formatNumber(meta.products);
  root.querySelector('#madad-authority-rows').textContent = formatNumber(meta.integratedRows);
  root.querySelector('#madad-authority-period').textContent =
    `${formatPeriod(meta.historyStart)} – ${formatPeriod(meta.historyEnd)}`;

  navigation.forEach((button) => {
    button.addEventListener('click', () => openView(button.dataset.authorityView));
  });
  searchInput.addEventListener('input', renderTable);
  districtSelect.addEventListener('change', renderTable);
  viewAllButton.addEventListener('click', () => {
    openView(currentView === 'warehouses' ? 'shortages' : 'warehouses');
  });

  openView('overview');
  if (window.lucide) window.lucide.createIcons();
})();
