(() => {
  const root = document.getElementById('madad-interfaces');
  const navigation = Array.from(root.querySelectorAll('[data-pharmacist-view]'));
  const panels = Array.from(root.querySelectorAll('[data-pharmacist-panel]'));
  const rawCatalog = Array.isArray(window.MADAD_MEDICINE_CATALOG) ? window.MADAD_MEDICINE_CATALOG : [];
  const sessionHistory = [];
  let selectedMedicine = null;

  const catalog = rawCatalog.map((record, index) => ({
    id: String(record.id ?? record.recordId ?? record.image_id ?? index + 1),
    label: String(record.label ?? record.classLabel ?? record.class_name ?? record.class ?? ''),
    name: String(record.name ?? record.medicineName ?? record.medicine_name ?? record.label ?? ''),
    description: String(record.description ?? record.caption ?? ''),
    strength: String(record.strength ?? ''),
    form: String(record.form ?? record.dosageForm ?? record.dosage_form ?? ''),
    image: String(record.image ?? record.imagePath ?? record.image_path ?? record.imageUrl ?? '')
  })).filter((record) => record.name || record.label);

  const views = {
    search: {
      title: 'Medicine Search',
      description: 'Search by medicine name and review its details.'
    },
    dispensing: {
      title: 'Dispensing Record',
      description: 'Enter patient and prescription details after selecting a medicine.'
    },
    history: {
      title: 'Patient History',
      description: 'Review dispensing records created in this browser session.'
    },
    catalog: {
      title: 'Medicine Catalog',
      description: 'Review the medicine information available to the pharmacist.'
    }
  };

  const setFeedback = (message, isError = false) => {
    const feedback = root.querySelector('#madad-pharmacist-feedback');
    feedback.textContent = message;
    feedback.classList.toggle('is-error', isError);
  };

  const openView = (viewName) => {
    const selected = views[viewName] ? viewName : 'search';
    const view = views[selected];
    navigation.forEach((button) => {
      button.classList.toggle('is-active', button.dataset.pharmacistView === selected);
    });
    panels.forEach((panel) => {
      panel.hidden = panel.dataset.pharmacistPanel !== selected;
    });
    root.querySelector('#madad-pharmacist-title').textContent = view.title;
    root.querySelector('#madad-pharmacist-description').textContent = view.description;

    if (selected === 'search') {
      setFeedback(catalog.length
        ? `${catalog.length} medicines are ready to search by name.`
        : 'Enter a medicine name to preview the search workflow.');
    } else if (selected === 'dispensing') {
      setFeedback(selectedMedicine
        ? `Dispensing form ready for ${selectedMedicine.name || selectedMedicine.label}.`
        : 'Select a medicine from Medicine Search before recording dispensing.', !selectedMedicine);
    } else if (selected === 'history') {
      renderHistory();
      setFeedback(`Patient History: ${sessionHistory.length} session record${sessionHistory.length === 1 ? '' : 's'}.`);
    } else {
      setFeedback(catalog.length
        ? `${catalog.length} medicines are available to search by name.`
        : 'The interface is ready for medicine-name search.');
    }
  };

  const clearMedicineResult = (message) => {
    selectedMedicine = null;
    const image = root.querySelector('#madad-medicine-image');
    image.hidden = true;
    image.removeAttribute('src');
    image.alt = '';
    root.querySelector('#madad-image-placeholder').hidden = false;
    root.querySelector('#madad-medicine-name').textContent = 'No medicine selected';
    root.querySelector('#madad-medicine-sub').textContent = 'Search by medicine name';
    root.querySelector('#madad-medicine-description').textContent = message;
    root.querySelector('#madad-medicine-label').textContent = '—';
    root.querySelector('#madad-medicine-strength').textContent = '—';
    root.querySelector('#madad-medicine-form').textContent = '—';
    root.querySelector('#madad-medicine-id').textContent = '—';
    root.querySelector('#madad-catalog-status').textContent = catalog.length ? 'No match' : 'Ready';
    root.querySelector('#madad-catalog-status').className =
      `madad-status ${catalog.length ? 'status-warn' : 'status-info'}`;
    root.querySelector('#madad-continue-dispensing').disabled = true;
    root.querySelector('#madad-selected-medicine-caption').textContent =
      'Select a medicine first';
  };

  const renderMedicine = (medicine) => {
    selectedMedicine = medicine;
    const image = root.querySelector('#madad-medicine-image');
    const placeholder = root.querySelector('#madad-image-placeholder');
    image.hidden = !medicine.image;
    placeholder.querySelector('span').textContent = medicine.image ? 'Reference photograph' : 'No reference photograph supplied for this product';
    placeholder.hidden = Boolean(medicine.image);

    if (medicine.image) {
      image.src = medicine.image;
      image.alt = `${medicine.name || medicine.label} medicine image`;
      image.onerror = () => {
        image.hidden = true;
        placeholder.hidden = false;
        placeholder.querySelector('span').textContent = 'Image path could not be loaded';
        setFeedback('The medicine record was found, but its image path could not be loaded.', true);
      };
    }

    root.querySelector('#madad-medicine-name').textContent = medicine.name || medicine.label;
    root.querySelector('#madad-medicine-sub').textContent =
      [medicine.strength, medicine.form].filter(Boolean).join(' · ') || 'Medicine details';
    root.querySelector('#madad-medicine-description').textContent =
      medicine.description || 'Description not available.';
    root.querySelector('#madad-medicine-label').textContent = medicine.label || 'Not provided';
    root.querySelector('#madad-medicine-strength').textContent = medicine.strength || 'Not provided';
    root.querySelector('#madad-medicine-form').textContent = medicine.form || 'Not provided';
    root.querySelector('#madad-medicine-id').textContent = medicine.id;
    root.querySelector('#madad-catalog-status').textContent = 'Selected for review';
    root.querySelector('#madad-catalog-status').className = 'madad-status status-good';
    root.querySelector('#madad-continue-dispensing').disabled = false;
    root.querySelector('#madad-selected-medicine-caption').textContent =
      `Selected medicine: ${medicine.name || medicine.label}`;
  };

  const searchMedicine = () => {
    const enteredName = root.querySelector('#madad-medicine-search').value.trim();
    const query = enteredName.toLowerCase();
    if (!enteredName) {
      setFeedback('Enter a medicine name.', true);
      return;
    }
    window.dispatchEvent(new Event('madad-name-search'));
    const matches = catalog.filter(record => (record.name + ' ' + record.id).toLowerCase().includes(query));
    clearMedicineResult('Choose a matching product and verify its details.');
    showCandidates(matches);
    setFeedback(matches.length ? `${matches.length} matching products. Select the correct NDC.` : 'No matching product in the catalog.', !matches.length);
  };
  function showCandidates(matches, predicted = false) {
    const box = document.getElementById('medicine-candidates'); box.replaceChildren();
    matches.forEach(item => {
      const medicine = predicted ? catalog.find(m => m.id === item.id) : item;
      if (!medicine) return;
      const button = document.createElement('button'); button.type = 'button'; button.className = 'madad-role-tab';
      button.textContent = `${medicine.name} · NDC ${medicine.id}` + (predicted ? ` · model score ${(item.score*100).toFixed(1)}%` : '');
      button.addEventListener('click', () => { renderMedicine(medicine); setFeedback('Selected dataset product. Verify the physical medicine and prescription before recording.'); });
      box.append(button);
    });
  }
  window.MadadMedicine = {
    clear: () => { clearMedicineResult('No medicine selected.'); document.getElementById('medicine-candidates').replaceChildren(); },
    candidates: matches => { clearMedicineResult('Image-based candidates are not a verified identification. Select only after checking the medicine.'); showCandidates(matches, true); }
  };

  const renderHistory = () => {
    const body = root.querySelector('#madad-patient-history-body');
    body.replaceChildren();
    if (!sessionHistory.length) {
      const row = document.createElement('tr');
      const cell = document.createElement('td');
      cell.colSpan = 5;
      const empty = document.createElement('div');
      empty.className = 'madad-empty-state';
      const title = document.createElement('strong');
      title.textContent = 'No session dispensing records';
      const message = document.createElement('span');
      message.textContent = 'Confirmed records will appear here until the page is refreshed.';
      empty.append(title, message);
      cell.appendChild(empty);
      row.appendChild(cell);
      body.appendChild(row);
      return;
    }

    sessionHistory.forEach((record) => {
      const row = document.createElement('tr');
      [record.patientId, record.patientName, record.medicine, record.quantity, record.prescription]
        .forEach((value, index) => {
          const cell = document.createElement('td');
          cell.textContent = value;
          if (index === 3) cell.classList.add('madad-number');
          row.appendChild(cell);
        });
      body.appendChild(row);
    });
  };

  navigation.forEach((button) => {
    button.addEventListener('click', () => openView(button.dataset.pharmacistView));
  });

  root.querySelector('#madad-medicine-button').addEventListener('click', searchMedicine);
  root.querySelector('#madad-medicine-search').addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      searchMedicine();
    }
  });
  root.querySelector('#madad-continue-dispensing').addEventListener('click', () => {
    if (!selectedMedicine) {
      setFeedback('Select a medicine before continuing.', true);
      return;
    }
    openView('dispensing');
    root.querySelector('#madad-patient-name').focus();
  });

  root.querySelector('#madad-dispensing-form').addEventListener('submit', (event) => {
    event.preventDefault();
    if (!selectedMedicine) {
      root.querySelector('#madad-dispensing-feedback').textContent =
        'No medicine is selected. Return to Medicine Search first.';
      setFeedback('Dispensing was not recorded because no medicine is selected.', true);
      return;
    }

    const quantity = Number(root.querySelector('#madad-dispense-quantity').value);
    if (!Number.isInteger(quantity) || quantity < 1) {
      root.querySelector('#madad-dispensing-feedback').textContent =
        'Enter a whole quantity of at least 1.';
      return;
    }

    sessionHistory.unshift({
      patientName: root.querySelector('#madad-patient-name').value.trim(),
      patientId: root.querySelector('#madad-patient-id').value.trim(),
      prescription: root.querySelector('#madad-prescription').value.trim(),
      quantity,
      medicine: `${selectedMedicine.name || selectedMedicine.label} · NDC ${selectedMedicine.id}`
    });
    root.querySelector('#madad-dispensing-feedback').textContent =
      'Record added to this session.';
    setFeedback('Dispensing record added to the current browser session.');
    event.currentTarget.reset();
  });

  root.querySelector('#madad-catalog-count').textContent = String(catalog.length);
  if (catalog.length) {
    root.querySelector('#madad-pharmacist-data-badge').textContent = 'Catalog Ready';
    const catalogMessage = root.querySelector('#madad-catalog-message');
    catalogMessage.querySelector('strong').textContent = 'Medicine catalog ready';
    catalogMessage.querySelector('span').textContent =
      `${catalog.length} medicines are searchable by name.`;
  }

  clearMedicineResult(
    catalog.length
      ? 'Enter a medicine name to display its available catalog details.'
      : 'The selected medicine details will appear here.'
  );
  renderHistory();
  openView('search');
  if (window.lucide) window.lucide.createIcons();
})();
