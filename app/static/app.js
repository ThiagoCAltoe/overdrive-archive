const $ = id => document.getElementById(id);

const PT_BR_TEXT = {
  'SELF-HOSTED VEHICLE ARCHIVE': 'ARQUIVO VEICULAR AUTO-HOSPEDADO',
  'Welcome back': 'Bem-vindo de volta',
  'Sign in to manage synchronization and private vehicle data.': 'Entre para gerenciar a sincronização e os dados privados do veículo.',
  'Sign-in method': 'Método de acesso',
  'Username': 'Usuário',
  'Password': 'Senha',
  'Request a one-time sign-in code.': 'Solicite um código de acesso de uso único.',
  'One-time code': 'Código de uso único',
  'Send code': 'Enviar código',
  'Sign in': 'Entrar',
  'Verify code': 'Verificar código',
  'Username & password': 'Usuário e senha',
  'Local administrator account': 'Conta de administrador local',
  'Telegram code': 'Código pelo Telegram',
  'One-time code sent to the configured Telegram chat': 'Código de uso único enviado ao chat configurado no Telegram',
  'WhatsApp code': 'Código pelo WhatsApp',
  'One-time code sent through the configured WhatsApp gateway': 'Código de uso único enviado pelo gateway configurado do WhatsApp',
  'One-time code sent': 'Código de uso único enviado',
  'Unofficial community project. Your data stays on your infrastructure.': 'Projeto comunitário não oficial. Seus dados permanecem na sua infraestrutura.',
  'Overdrive Archive home': 'Início do Overdrive Archive',
  'Primary navigation': 'Navegação principal',
  'Overview': 'Visão geral',
  'Archive': 'Arquivo',
  'Settings': 'Configurações',
  'Self-hosted': 'Auto-hospedado',
  'Sign out': 'Sair',
  'Open navigation': 'Abrir navegação',
  'ARCHIVE CONTROL CENTER': 'CENTRAL DO ARQUIVO',
  'Idle': 'Ocioso',
  'Sync now': 'Sincronizar agora',
  'Ready to connect': 'Pronto para conectar',
  'Your vehicle data.': 'Os dados do seu veículo.',
  'Your infrastructure.': 'Na sua infraestrutura.',
  'Archive recordings, trips, charging sessions and configuration snapshots on a local disk or mounted NAS.': 'Arquive gravações, viagens, sessões de recarga e snapshots de configuração em um disco local ou NAS montado.',
  'Start synchronization': 'Iniciar sincronização',
  'Configure source': 'Configurar origem',
  'VEHICLE': 'VEÍCULO',
  'ARCHIVE': 'ARQUIVO',
  'Archive summary': 'Resumo do arquivo',
  'Archived items': 'Itens arquivados',
  'No categories yet': 'Nenhuma categoria ainda',
  'Primary content size': 'Tamanho do conteúdo',
  'Videos and archived snapshots': 'Vídeos e snapshots arquivados',
  'Last synchronization': 'Última sincronização',
  'Never': 'Nunca',
  'No run recorded': 'Nenhuma execução registrada',
  'Next scheduled run': 'Próxima execução agendada',
  'Manual': 'Manual',
  'Wi-Fi policy enabled': 'Política de Wi-Fi ativada',
  'RECENT ACTIVITY': 'ATIVIDADE RECENTE',
  'Synchronization runs': 'Execuções de sincronização',
  'Refresh': 'Atualizar',
  'Started': 'Início',
  'Trigger': 'Origem',
  'Result': 'Resultado',
  'New': 'Novos',
  'Transferred': 'Transferido',
  'Details': 'Detalhes',
  'No synchronization runs yet.': 'Nenhuma sincronização executada ainda.',
  'DATA INVENTORY': 'INVENTÁRIO DE DADOS',
  'Archive categories': 'Categorias do arquivo',
  'Archived data will appear here.': 'Os dados arquivados aparecerão aqui.',
  'BROWSE & PLAY': 'NAVEGAR E REPRODUZIR',
  'Archive library': 'Biblioteca do arquivo',
  'Scan visual previews, filter recording types, and play archived media without leaving the library.': 'Veja miniaturas, filtre os tipos de gravação e reproduza a mídia sem sair da biblioteca.',
  'Refresh library': 'Atualizar biblioteca',
  'Category': 'Categoria',
  'All categories': 'Todas as categorias',
  'Recordings': 'Gravações',
  'Trips': 'Viagens',
  'Charging': 'Recarga',
  'Automations': 'Automações',
  'Key mappings': 'Mapeamento de teclas',
  'Telemetry': 'Telemetria',
  'Configuration': 'Configuração',
  'Recording type': 'Tipo de gravação',
  'All recording types': 'Todos os tipos de gravação',
  'ACC / drive': 'ACC / condução',
  'Surveillance': 'Vigilância',
  'Proximity': 'Proximidade',
  'OEM dashcam': 'Câmera OEM',
  'Search': 'Pesquisar',
  'VISUAL ARCHIVE': 'ARQUIVO VISUAL',
  'Loading archived items…': 'Carregando itens arquivados…',
  'Private previews from your archive': 'Miniaturas privadas do seu arquivo',
  'No archived items match these filters.': 'Nenhum item arquivado corresponde a estes filtros.',
  'SYNC POLICY': 'POLÍTICA DE SINCRONIZAÇÃO',
  'Every policy is configurable. Nothing here changes the current Overdrive configuration in your vehicle.': 'Todas as políticas são configuráveis. Nada aqui altera a configuração atual do Overdrive no veículo.',
  'Save & test connection': 'Salvar e testar conexão',
  'Save settings': 'Salvar configurações',
  'Interface': 'Interface',
  'Choose the language used by this installation.': 'Escolha o idioma usado por esta instalação.',
  'Interface language': 'Idioma da interface',
  'English': 'Inglês',
  'Vehicle connection': 'Conexão com o veículo',
  'Connect through a trusted LAN address or private VPN such as Tailscale.': 'Conecte por uma rede local confiável ou VPN privada, como o Tailscale.',
  'Vehicle name': 'Nome do veículo',
  'Overdrive URL': 'URL do Overdrive',
  'Access code, full token, or bearer JWT': 'Código de acesso, token completo ou JWT bearer',
  'Import the available Overdrive profile': 'Importar o perfil disponível no Overdrive',
  "Refreshes device and version details, and fills empty model fields from Overdrive's selected visual profile. Manual values are preserved.": 'Atualiza os dados do dispositivo e da versão e preenche campos vazios do modelo usando o perfil visual selecionado no Overdrive. Valores manuais são preservados.',
  'Vehicle model': 'Modelo do veículo',
  'Model ID': 'ID do modelo',
  'Drive side': 'Lado da direção',
  'Unknown / automatic': 'Desconhecido / automático',
  'Left-hand drive': 'Volante à esquerda',
  'Right-hand drive': 'Volante à direita',
  'Vehicle color': 'Cor do veículo',
  'Detected device ID': 'ID do dispositivo detectado',
  'Detected Overdrive version': 'Versão detectada do Overdrive',
  'Verify TLS certificates': 'Verificar certificados TLS',
  'Keep enabled for HTTPS. Disable only for a trusted self-signed endpoint.': 'Mantenha ativado para HTTPS. Desative somente para um endpoint confiável com certificado autoassinado.',
  'Request timeout (seconds)': 'Tempo limite da requisição (segundos)',
  'Schedule & network': 'Agendamento e rede',
  'Run manually, on an interval, or once per day.': 'Execute manualmente, em intervalos ou uma vez por dia.',
  'Enable automatic synchronization': 'Ativar sincronização automática',
  'Manual synchronization remains available when disabled.': 'A sincronização manual continua disponível quando desativada.',
  'Schedule mode': 'Modo de agendamento',
  'Manual only': 'Somente manual',
  'Every interval': 'A cada intervalo',
  'Daily at a specific time': 'Diariamente em horário específico',
  'Every': 'A cada',
  'Unit': 'Unidade',
  'Minutes': 'Minutos',
  'Hours': 'Horas',
  'Days': 'Dias',
  'Daily time': 'Horário diário',
  'Timezone': 'Fuso horário',
  'Download only while the vehicle is on Wi-Fi': 'Baixar somente quando o veículo estiver no Wi-Fi',
  'Turn this off to allow synchronization on any network reported by Overdrive.': 'Desative para permitir sincronização em qualquer rede informada pelo Overdrive.',
  'Allowed Wi-Fi networks (optional)': 'Redes Wi-Fi permitidas (opcional)',
  'One SSID per line. Leave empty to allow every Wi-Fi network.': 'Um SSID por linha. Deixe vazio para permitir qualquer rede Wi-Fi.',
  'Data selection': 'Seleção de dados',
  'Select exactly what should be archived.': 'Selecione exatamente o que deve ser arquivado.',
  'Categories': 'Categorias',
  'ACC, replay, surveillance and dashcam': 'ACC, replay, vigilância e dashcam',
  'Trip summary and statistics': 'Resumo e estatísticas das viagens',
  'Sessions and charging history': 'Sessões e histórico de recarga',
  'Read-only automation snapshot': 'Snapshot somente leitura das automações',
  'Buttons and assigned actions': 'Botões e ações atribuídas',
  'Live snapshot and trip telemetry': 'Snapshot ao vivo e telemetria das viagens',
  'Experimental hazard export': 'Exportação experimental de riscos',
  'Redacted settings only': 'Somente configurações sanitizadas',
  'Recording types': 'Tipos de gravação',
  'Instant replay': 'Replay instantâneo',
  'Automatically include new recording types': 'Incluir automaticamente novos tipos de gravação',
  'Preserves and tags recording types introduced by future Overdrive releases, even before this archive UI knows their friendly name.': 'Preserva e identifica tipos introduzidos por futuras versões do Overdrive, mesmo antes de esta interface conhecer o nome amigável.',
  'Surveillance severity': 'Severidade da vigilância',
  'Notice': 'Aviso',
  'Alert': 'Alerta',
  'Critical': 'Crítico',
  'Download thumbnails': 'Baixar miniaturas',
  'Stores the best available preview next to each video.': 'Armazena a melhor miniatura disponível junto de cada vídeo.',
  'Download event timelines': 'Baixar linhas do tempo dos eventos',
  'Stores available detection metadata next to surveillance clips.': 'Armazena os metadados de detecção disponíveis junto dos vídeos de vigilância.',
  'Destination': 'Destino',
  'The MVP writes to a local filesystem. Mount an NFS or SMB share into Docker to use a NAS.': 'O MVP grava no sistema de arquivos local. Monte um compartilhamento NFS ou SMB no Docker para usar um NAS.',
  'Local / mounted NAS': 'Local / NAS montado',
  'Streaming writes, SHA-256 checksums and atomic finalization': 'Gravação em streaming, checksums SHA-256 e finalização atômica',
  'Archive subdirectory': 'Subdiretório do arquivo',
  'Created below the Docker archive volume.': 'Criado dentro do volume de arquivo do Docker.',
  'Container archive root': 'Raiz do arquivo no container',
  'Destination roadmap': 'Evolução dos destinos',
  'SFTP, WebDAV and S3-compatible storage are planned as separate adapters.': 'Armazenamentos SFTP, WebDAV e compatíveis com S3 estão planejados como adaptadores separados.',
  'Authentication': 'Autenticação',
  'The installer chooses which sign-in methods are available. Local password is the default; Telegram and WhatsApp are optional.': 'O instalador escolhe os métodos de acesso disponíveis. Senha local é o padrão; Telegram e WhatsApp são opcionais.',
  'Provider configuration': 'Configuração dos provedores',
  'Provider secrets are supplied through Docker environment variables or secrets, so bot tokens never appear in the browser or public repository.': 'Os segredos dos provedores são fornecidos por variáveis de ambiente ou secrets do Docker, então tokens de bots nunca aparecem no navegador nem no repositório público.',
  'Changes are stored only in this new archive application.': 'As alterações são armazenadas somente neste novo aplicativo de arquivo.',
  'ARCHIVED RECORDING': 'GRAVAÇÃO ARQUIVADA',
  'Recording': 'Gravação',
  'Recorded': 'Gravado em',
  'Vehicle': 'Veículo',
  'File size': 'Tamanho do arquivo',
  'Integrity': 'Integridade',
  'Download MP4': 'Baixar MP4',
  'Close': 'Fechar',
  'Archived recording': 'Gravação arquivada',
  'Camera view': 'Visualização da câmera',
  'Playback controls': 'Controles de reprodução',
  'All': 'Todas',
  'Front': 'Frontal',
  'Right': 'Direita',
  'Rear': 'Traseira',
  'Left': 'Esquerda',
  'All cameras': 'Todas as câmeras',
  'Front camera': 'Câmera frontal',
  'Right camera': 'Câmera direita',
  'Rear camera': 'Câmera traseira',
  'Left camera': 'Câmera esquerda',
  'Showing': 'Exibindo',
  'Pause': 'Pausar',
  'Mute': 'Silenciar',
  'Unmute': 'Ativar som',
  'Enter fullscreen': 'Entrar em tela cheia',
  'Exit fullscreen': 'Sair da tela cheia',
  'Seek recording': 'Buscar na gravação',
  'of': 'de',
  'Filename or vehicle': 'Nome do arquivo ou veículo',
  'My vehicle': 'Meu veículo',
  'Leave blank to keep the saved credential': 'Deixe em branco para manter a credencial salva',
  'Imported profile or manual value': 'Perfil importado ou valor manual',
  'e.g. dolphin, seagull, atto3': 'ex.: dolphin, seagull, atto3',
  'Not detected yet': 'Ainda não detectado',
  'A credential is saved. Leave this blank to keep it.': 'Uma credencial está salva. Deixe em branco para mantê-la.',
  'No credential saved.': 'Nenhuma credencial salva.',
  'Settings loaded.': 'Configurações carregadas.',
  'Settings saved.': 'Configurações salvas.',
  'Settings saved': 'Configurações salvas',
  'Enabled': 'Ativado',
  'No authentication method is configured.': 'Nenhum método de autenticação está configurado.',
  'Testing…': 'Testando…',
  'Connection test failed': 'O teste de conexão falhou',
  'Overdrive authentication failed (HTTP 401).': 'A autenticação no Overdrive falhou (HTTP 401).',
  'Overdrive refused access (HTTP 403).': 'O Overdrive recusou o acesso (HTTP 403).',
  'The requested Overdrive API is unavailable (HTTP 404).': 'A API solicitada do Overdrive não está disponível (HTTP 404).',
  'Could not reach the vehicle. Check its URL, network, VPN, and availability.': 'Não foi possível acessar o veículo. Verifique a URL, a rede, a VPN e a disponibilidade.',
  'Synchronization started': 'Sincronização iniciada',
  'Synchronizing': 'Sincronizando',
  'Synchronizing…': 'Sincronizando…',
  'Play recording': 'Reproduzir gravação',
  'Download': 'Baixar',
  'Open file': 'Abrir arquivo',
  'No archived items found': 'Nenhum item arquivado encontrado',
  'Connected': 'Conectado',
  'Play': 'Reproduzir',
  'Open': 'Abrir',
  'Unknown': 'Desconhecido',
  'Wi-Fi': 'Wi-Fi',
  'wifi': 'Wi-Fi',
  'cellular': 'rede móvel',
  'Unknown recording type': 'Tipo de gravação desconhecido',
  'Any network allowed': 'Qualquer rede permitida',
  'active categories': 'categorias ativas',
  'archived item': 'item arquivado',
  'archived items': 'itens arquivados',
  'new': 'novos',
  'success': 'sucesso',
  'failed': 'falhou',
  'partial': 'parcial',
  'skipped': 'ignorado',
  'running': 'em execução',
  'manual': 'manual',
  'schedule': 'agendamento',
  'sample import': 'importação de amostra',
  'unknown': 'desconhecido',
};

const originalTextNodes = new WeakMap();
const originalAttributes = new WeakMap();

function savedLanguage() {
  try { return localStorage.getItem('overdriveArchiveLanguage') || 'en'; } catch { return 'en'; }
}

const state = {
  overviewTimer: null,
  settings: null,
  currentView: 'overview',
  authMethods: [],
  authMethod: 'local',
  language: ['en', 'pt-BR'].includes(savedLanguage()) ? savedLanguage() : 'en',
  lastOverview: null,
  lastLibraryItems: null,
  playerCameraView: 'all',
  playerCameraLayout: 'standard',
};

const viewMeta = {
  overview: ['ARCHIVE CONTROL CENTER', 'Overview'],
  library: ['BROWSE & PLAY', 'Archive'],
  settings: ['SYNC POLICY', 'Settings'],
};

const playerCameraViews = ['all', 'front', 'right', 'rear', 'left'];
const playerCameraLabels = {
  all: 'All cameras',
  front: 'Front camera',
  right: 'Right camera',
  rear: 'Rear camera',
  left: 'Left camera',
};

function t(value) {
  return state.language === 'pt-BR' ? (PT_BR_TEXT[value] || value) : value;
}

function locale() {
  return state.language === 'pt-BR' ? 'pt-BR' : 'en';
}

function translateStaticDocument() {
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  nodes.forEach(node => {
    if (node.parentElement?.closest('script, style')) return;
    if (!originalTextNodes.has(node)) originalTextNodes.set(node, node.nodeValue);
    const original = originalTextNodes.get(node);
    const trimmed = original.trim();
    if (!trimmed) return;
    const translated = t(trimmed);
    node.nodeValue = original.replace(trimmed, translated);
  });

  document.querySelectorAll('[placeholder], [aria-label], [title]').forEach(element => {
    if (!originalAttributes.has(element)) {
      originalAttributes.set(element, {
        placeholder: element.getAttribute('placeholder'),
        ariaLabel: element.getAttribute('aria-label'),
        title: element.getAttribute('title'),
      });
    }
    const original = originalAttributes.get(element);
    if (original.placeholder !== null) element.setAttribute('placeholder', t(original.placeholder));
    if (original.ariaLabel !== null) element.setAttribute('aria-label', t(original.ariaLabel));
    if (original.title !== null) element.setAttribute('title', t(original.title));
  });
}

function applyLanguage(language, { rerender = true } = {}) {
  state.language = language === 'pt-BR' ? 'pt-BR' : 'en';
  document.documentElement.lang = state.language;
  try { localStorage.setItem('overdriveArchiveLanguage', state.language); } catch {}
  translateStaticDocument();
  if ($('interface-language')) $('interface-language').value = state.language;
  const meta = viewMeta[state.currentView];
  if (meta) {
    $('page-eyebrow').textContent = t(meta[0]);
    $('page-title').textContent = t(meta[1]);
  }
  updatePlayerControls();
  updatePlayerTimeline();
  if ($('player-dialog').open) announcePlayerCameraView();
  if (!rerender) return;
  if (state.authMethods.length) renderAuthMethods({ methods: state.authMethods });
  if (state.lastOverview) renderOverview(state.lastOverview);
  if (state.lastLibraryItems) renderLibrary(state.lastLibraryItems);
  if (state.settings?.runtime?.auth) renderAuthSummary(state.settings.runtime.auth.methods || []);
}

function toast(message) {
  const element = $('toast');
  element.textContent = message;
  element.classList.add('show');
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => element.classList.remove('show'), 3200);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    credentials: 'same-origin',
    cache: 'no-store',
    ...options,
    headers: {
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...(options.headers || {}),
    },
  });
  let payload = {};
  try { payload = await response.json(); } catch {}
  if (response.status === 401 && !['/api/login', '/api/auth/verify-code'].includes(path)) {
    showLogin();
    throw new Error('Authentication required');
  }
  if (!response.ok) throw new Error(payload.error || payload.message || `Request failed (${response.status})`);
  return payload;
}

function renderAuthMethods(auth) {
  state.authMethods = Array.isArray(auth?.methods) ? auth.methods : [];
  if (!state.authMethods.some(method => method.id === state.authMethod)) {
    state.authMethod = state.authMethods[0]?.id || 'local';
  }
  const container = $('auth-methods');
  container.replaceChildren();
  state.authMethods.forEach(method => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = `auth-method${method.id === state.authMethod ? ' active' : ''}`;
    button.textContent = t(method.label);
    button.title = t(method.description || '');
    button.addEventListener('click', () => {
      state.authMethod = method.id;
      renderAuthMethods({ methods: state.authMethods });
    });
    container.append(button);
  });
  const local = state.authMethod === 'local';
  $('local-login-fields').classList.toggle('hidden', !local);
  $('otp-login-fields').classList.toggle('hidden', local);
  const selected = state.authMethods.find(method => method.id === state.authMethod);
  $('otp-description').textContent = t(selected?.description || 'Request a one-time sign-in code.');
  $('login-button').textContent = t(local ? 'Sign in' : 'Verify code');
}

async function showLogin(auth = null) {
  $('app-shell').classList.add('hidden');
  $('login-screen').classList.remove('hidden');
  clearTimeout(state.overviewTimer);
  if (!auth) {
    try { auth = await api('/api/auth/options'); } catch { auth = { methods: [{ id: 'local', label: 'Username & password' }] }; }
  }
  renderAuthMethods(auth);
  setTimeout(() => (state.authMethod === 'local' ? $('login-username') : $('login-code')).focus(), 0);
}

function showApp() {
  $('login-screen').classList.add('hidden');
  $('app-shell').classList.remove('hidden');
  loadOverview();
}

function setView(name) {
  if (!viewMeta[name]) return;
  if (name !== 'library' && $('player-dialog').open) closePlayer();
  state.currentView = name;
  document.querySelectorAll('.view').forEach(view => view.classList.toggle('active', view.id === `view-${name}`));
  document.querySelectorAll('.nav-link').forEach(link => link.classList.toggle('active', link.dataset.viewTarget === name));
  $('page-eyebrow').textContent = t(viewMeta[name][0]);
  $('page-title').textContent = t(viewMeta[name][1]);
  document.body.classList.remove('nav-open');
  if (name === 'library') loadLibrary();
  if (name === 'settings') loadSettings();
}

function formatBytes(bytes) {
  const value = Number(bytes) || 0;
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  if (value <= 0) return '0 B';
  const index = Math.min(units.length - 1, Math.floor(Math.log(value) / Math.log(1024)));
  return `${(value / (1024 ** index)).toLocaleString(locale(), { maximumFractionDigits: index > 1 ? 2 : 0 })} ${units[index]}`;
}

function relativeTime(value) {
  if (!value) return t('Never');
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return t('Unknown');
  const seconds = Math.round((date.getTime() - Date.now()) / 1000);
  const formatter = new Intl.RelativeTimeFormat(locale(), { numeric: 'auto' });
  const absolute = Math.abs(seconds);
  if (absolute < 60) return formatter.format(seconds, 'second');
  if (absolute < 3600) return formatter.format(Math.round(seconds / 60), 'minute');
  if (absolute < 86400) return formatter.format(Math.round(seconds / 3600), 'hour');
  return formatter.format(Math.round(seconds / 86400), 'day');
}

function exactTime(value) {
  if (!value) return '—';
  const numeric = Number(value);
  const normalized = Number.isFinite(numeric) && numeric > 0 && numeric < 1e10
    ? numeric * 1000
    : value;
  const date = new Date(normalized);
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString(locale(), { dateStyle: 'medium', timeStyle: 'short' });
}

function title(value) {
  return String(value || '').replaceAll('_', ' ').replace(/\b\w/g, letter => letter.toUpperCase());
}

function labelFor(value) {
  const normalized = String(value || '');
  const labels = {
    recordings: 'Recordings',
    trips: 'Trips',
    charging: 'Charging',
    automations: 'Automations',
    key_mappings: 'Key mappings',
    telemetry: 'Telemetry',
    roadsense: 'RoadSense',
    configuration: 'Configuration',
    manual: 'Manual',
    schedule: 'schedule',
    sample_import: 'sample import',
    'sample-import': 'sample import',
    wifi: 'wifi',
    cellular: 'cellular',
    success: 'success',
    failed: 'failed',
    partial: 'partial',
    skipped: 'skipped',
    running: 'running',
    unknown: 'unknown',
  };
  return t(labels[normalized] || title(normalized));
}

function recordingSubtypeLabel(value) {
  return t({
    replay: 'Replay',
    drive: 'ACC / drive',
    surveillance: 'Surveillance',
    proximity: 'Proximity',
    oem_dashcam: 'OEM dashcam',
    unknown: 'Unknown recording type',
  }[value] || title(value));
}

function badge(status) {
  const element = document.createElement('span');
  element.className = `badge ${status || 'skipped'}`;
  element.textContent = labelFor(status || 'unknown');
  return element;
}

function renderRuns(runs) {
  const body = $('runs-body');
  body.replaceChildren();
  $('runs-empty').classList.toggle('hidden', runs.length > 0);
  runs.forEach(run => {
    const row = document.createElement('tr');
    const started = document.createElement('td');
    started.textContent = exactTime(run.started_at);
    started.title = run.started_at || '';
    const reason = document.createElement('td');
    reason.textContent = labelFor(run.reason);
    const result = document.createElement('td');
    result.append(badge(run.status));
    const added = document.createElement('td');
    added.textContent = String(run.items_added ?? 0);
    const transferred = document.createElement('td');
    transferred.textContent = formatBytes(run.bytes_added);
    const details = document.createElement('td');
    details.textContent = run.message || '—';
    row.append(started, reason, result, added, transferred, details);
    body.append(row);
  });
}

function renderCategories(categories) {
  const container = $('category-list');
  container.replaceChildren();
  $('categories-empty').classList.toggle('hidden', categories.length > 0);
  categories.forEach(category => {
    const item = document.createElement('div');
    item.className = 'category-item';
    const icon = document.createElement('span');
    icon.textContent = category.category === 'recordings' ? '▶' : '{}';
    const copy = document.createElement('div');
    const name = document.createElement('strong');
    name.textContent = labelFor(category.category);
    const count = document.createElement('small');
    count.textContent = state.language === 'pt-BR'
      ? `${category.count} ${category.count === 1 ? t('archived item') : t('archived items')}`
      : `${category.count} archived item${category.count === 1 ? '' : 's'}`;
    copy.append(name, count);
    const size = document.createElement('em');
    size.textContent = formatBytes(category.bytes);
    item.append(icon, copy, size);
    container.append(item);
  });
}

function renderOverview(data) {
  state.lastOverview = data;
  const stats = data.stats || {};
  const runs = Array.isArray(data.runs) ? data.runs : [];
  const sync = data.sync || {};
  const latest = runs[0];
  $('metric-items').textContent = Number(stats.item_count || 0).toLocaleString(locale());
  $('metric-storage').textContent = formatBytes(stats.total_bytes);
  $('metric-categories').textContent = stats.categories?.length
    ? (state.language === 'pt-BR'
      ? `${stats.categories.length} ${t('active categories')}`
      : `${stats.categories.length} active categories`)
    : t('No categories yet');
  $('metric-last-sync').textContent = latest ? relativeTime(latest.finished_at || latest.started_at) : t('Never');
  $('metric-last-result').textContent = latest
    ? `${labelFor(latest.status)} · ${latest.items_added || 0} ${t('new')}`
    : t('No run recorded');
  $('metric-next-sync').textContent = sync.next_run_at ? relativeTime(sync.next_run_at) : t('Manual');
  $('metric-policy').textContent = state.settings?.schedule?.only_wifi === false ? t('Any network allowed') : t('Wi-Fi policy enabled');
  const active = Boolean(sync.active);
  const chip = $('sync-chip');
  chip.className = `status-chip${active ? ' running' : ''}`;
  chip.querySelector('strong').textContent = active ? t(sync.current || 'Synchronizing') : t('Idle');
  [$('sync-now-top'), $('sync-now-hero')].forEach(button => {
    button.disabled = active;
    button.textContent = active ? t('Synchronizing…') : t(button.id === 'sync-now-hero' ? 'Start synchronization' : 'Sync now');
  });
  renderRuns(runs);
  renderCategories(Array.isArray(stats.categories) ? stats.categories : []);
  clearTimeout(state.overviewTimer);
  state.overviewTimer = setTimeout(loadOverview, active ? 4000 : 15000);
}

async function loadOverview() {
  try {
    const data = await api('/api/overview');
    renderOverview(data);
  } catch (error) {
    if (error.message !== 'Authentication required') toast(error.message);
    clearTimeout(state.overviewTimer);
    state.overviewTimer = setTimeout(loadOverview, 15000);
  }
}

async function runSync() {
  try {
    await api('/api/sync', { method: 'POST', body: '{}' });
    toast(t('Synchronization started'));
    loadOverview();
  } catch (error) {
    toast(error.message);
  }
}

function selectedValues(containerId) {
  return [...document.querySelectorAll(`#${containerId} input[type="checkbox"]:checked`)].map(input => input.value);
}

function setSelected(containerId, values) {
  const selected = new Set(values || []);
  document.querySelectorAll(`#${containerId} input[type="checkbox"]`).forEach(input => {
    input.checked = selected.has(input.value);
  });
}

function updateScheduleVisibility() {
  const mode = $('schedule-mode').value;
  $('interval-fields').classList.toggle('hidden', mode !== 'interval');
  $('daily-field').classList.toggle('hidden', mode !== 'daily');
}

function populateSettings(settings) {
  state.settings = settings;
  const interfaceSettings = settings.interface || {};
  const vehicle = settings.vehicle || {};
  const schedule = settings.schedule || {};
  const content = settings.content || {};
  const configuredLanguage = interfaceSettings.language || 'en';
  $('interface-language').value = configuredLanguage;
  applyLanguage(configuredLanguage, { rerender: false });
  $('vehicle-name').value = vehicle.name || '';
  $('vehicle-url').value = vehicle.base_url || '';
  $('vehicle-token').value = '';
  $('token-state').textContent = vehicle.device_token_configured ? t('A credential is saved. Leave this blank to keep it.') : t('No credential saved.');
  $('auto-detect-profile').checked = Boolean(vehicle.auto_detect_profile);
  $('vehicle-model-name').value = vehicle.model_name || '';
  $('vehicle-model-id').value = vehicle.model_id || '';
  $('vehicle-drive-side').value = vehicle.drive_side || '';
  $('vehicle-color').value = vehicle.color || '';
  $('vehicle-device-id').value = vehicle.device_id || t('Not detected yet');
  $('vehicle-app-version').value = vehicle.app_version || t('Not detected yet');
  const vehicleLabel = vehicle.model_name || vehicle.name || t('Vehicle');
  $('vehicle-state').lastChild.textContent = ` ${vehicleLabel}`;
  $('verify-tls').checked = Boolean(vehicle.verify_tls);
  $('request-timeout').value = vehicle.request_timeout_seconds || 30;
  $('schedule-enabled').checked = Boolean(schedule.enabled);
  $('schedule-mode').value = schedule.mode || 'manual';
  $('interval-value').value = schedule.interval_value || 6;
  $('interval-unit').value = schedule.interval_unit || 'hours';
  $('daily-time').value = schedule.daily_time || '02:00';
  $('schedule-timezone').value = schedule.timezone || 'UTC';
  $('only-wifi').checked = Boolean(schedule.only_wifi);
  $('allowed-ssids').value = (schedule.allowed_ssids || []).join('\n');
  setSelected('category-options', content.categories);
  setSelected('recording-options', content.recording_types);
  $('include-unknown-recording-types').checked = Boolean(content.include_unknown_recording_types);
  setSelected('severity-options', content.severities);
  $('include-thumbnails').checked = Boolean(content.include_thumbnails);
  $('include-timeline').checked = Boolean(content.include_event_timeline);
  $('archive-subdirectory').value = settings.destination?.subdirectory || 'vehicles';
  $('archive-root').value = settings.runtime?.archive_root || '/archive';
  renderAuthSummary(settings.runtime?.auth?.methods || []);
  $('settings-status').textContent = t('Settings loaded.');
  updateScheduleVisibility();
  if (state.lastOverview) renderOverview(state.lastOverview);
  if (state.lastLibraryItems) renderLibrary(state.lastLibraryItems);
}

function renderAuthSummary(methods) {
  const container = $('auth-method-summary');
  container.replaceChildren();
  methods.forEach(method => {
    const item = document.createElement('div');
    item.className = 'auth-summary-item';
    const status = document.createElement('em');
    status.textContent = t('Enabled');
    const name = document.createElement('strong');
    name.textContent = t(method.label);
    const description = document.createElement('small');
    description.textContent = t(method.description || '');
    item.append(status, name, description);
    container.append(item);
  });
  if (!methods.length) {
    const empty = document.createElement('div');
    empty.className = 'empty-state';
    empty.textContent = t('No authentication method is configured.');
    container.append(empty);
  }
}

async function loadSettings() {
  try {
    const settings = await api('/api/settings');
    populateSettings(settings);
  } catch (error) {
    toast(error.message);
  }
}

function settingsPayload() {
  return {
    interface: {
      language: $('interface-language').value,
    },
    vehicle: {
      name: $('vehicle-name').value,
      base_url: $('vehicle-url').value,
      device_token: $('vehicle-token').value,
      verify_tls: $('verify-tls').checked,
      request_timeout_seconds: Number($('request-timeout').value),
      auto_detect_profile: $('auto-detect-profile').checked,
      model_name: $('vehicle-model-name').value,
      model_id: $('vehicle-model-id').value,
      drive_side: $('vehicle-drive-side').value,
      color: $('vehicle-color').value,
      device_id: state.settings?.vehicle?.device_id || '',
      app_version: state.settings?.vehicle?.app_version || '',
      locale: state.settings?.vehicle?.locale || '',
      distance_unit: state.settings?.vehicle?.distance_unit || '',
    },
    schedule: {
      enabled: $('schedule-enabled').checked,
      mode: $('schedule-mode').value,
      interval_value: Number($('interval-value').value),
      interval_unit: $('interval-unit').value,
      daily_time: $('daily-time').value,
      timezone: $('schedule-timezone').value,
      only_wifi: $('only-wifi').checked,
      allowed_ssids: $('allowed-ssids').value.split(/[\n,]/).map(value => value.trim()).filter(Boolean),
    },
    content: {
      categories: selectedValues('category-options'),
      recording_types: selectedValues('recording-options'),
      include_unknown_recording_types: $('include-unknown-recording-types').checked,
      severities: selectedValues('severity-options'),
      include_thumbnails: $('include-thumbnails').checked,
      include_event_timeline: $('include-timeline').checked,
    },
    destination: {
      type: 'local',
      subdirectory: $('archive-subdirectory').value,
    },
  };
}

async function saveSettings(showMessage = true) {
  const buttons = [$('save-settings-top'), $('save-settings-bottom'), $('test-connection')];
  buttons.forEach(button => button.disabled = true);
  try {
    const response = await api('/api/settings', { method: 'PUT', body: JSON.stringify(settingsPayload()) });
    state.settings = { ...response.settings, runtime: state.settings?.runtime || {} };
    $('vehicle-token').value = '';
    applyLanguage(response.settings.interface?.language || 'en');
    $('token-state').textContent = response.settings.vehicle.device_token_configured ? t('A credential is saved. Leave this blank to keep it.') : t('No credential saved.');
    $('settings-status').textContent = t('Settings saved.');
    if (showMessage) toast(t('Settings saved'));
    loadOverview();
    return true;
  } catch (error) {
    $('settings-status').textContent = error.message;
    toast(error.message);
    return false;
  } finally {
    buttons.forEach(button => button.disabled = false);
  }
}

async function testConnection() {
  if (!await saveSettings(false)) return;
  $('test-connection').disabled = true;
  $('test-connection').textContent = t('Testing…');
  try {
    const response = await api('/api/test-connection', { method: 'POST', body: '{}' });
    const network = response.network || {};
    if (response.settings) populateSettings({ ...response.settings, runtime: state.settings?.runtime || {} });
    toast(`${t('Connected')} · ${labelFor(network.type)}${network.ssid ? ` · ${network.ssid}` : ''}`);
    $('vehicle-state').classList.remove('offline');
    $('vehicle-state').lastChild.textContent = ` ${t('Connected')} · ${labelFor(network.type)}`;
  } catch (error) {
    toast(error.message);
    $('vehicle-state').classList.add('offline');
    $('vehicle-state').lastChild.textContent = ` ${t('Connection test failed')}`;
  } finally {
    $('test-connection').disabled = false;
    $('test-connection').textContent = t('Save & test connection');
  }
}

async function loadLibrary() {
  updateRecordingTypeFilterState();
  $('library-grid').setAttribute('aria-busy', 'true');
  const params = new URLSearchParams();
  if ($('library-category').value) params.set('category', $('library-category').value);
  if ($('library-recording-type').value) params.set('subtype', $('library-recording-type').value);
  if ($('library-search').value.trim()) params.set('q', $('library-search').value.trim());
  params.set('limit', '200');
  try {
    const data = await api(`/api/items?${params}`);
    renderRecordingTypeFilter(data.recording_types || []);
    renderLibrary(data.items || []);
  } catch (error) {
    $('library-grid').setAttribute('aria-busy', 'false');
    toast(error.message);
  }
}

function updateRecordingTypeFilterState() {
  const select = $('library-recording-type');
  const category = $('library-category').value;
  const enabled = !category || category === 'recordings';
  select.disabled = !enabled;
  if (!enabled) select.value = '';
}

function renderRecordingTypeFilter(types) {
  const select = $('library-recording-type');
  const selected = select.value;
  const known = new Set([...select.options].map(option => option.value));
  types.forEach(typeRow => {
    const value = String(typeRow.subtype || '');
    if (!value || known.has(value)) return;
    const option = document.createElement('option');
    option.value = value;
    option.textContent = recordingSubtypeLabel(value);
    select.append(option);
    known.add(value);
  });
  select.value = selected;
}

function renderLibrary(items) {
  state.lastLibraryItems = items;
  const grid = $('library-grid');
  grid.replaceChildren();
  grid.setAttribute('aria-busy', 'false');
  $('library-empty').classList.toggle('hidden', items.length > 0);
  const totalBytes = items.reduce((total, item) => total + (Number(item.size_bytes) || 0), 0);
  $('library-summary').textContent = items.length
    ? (state.language === 'pt-BR'
      ? `${items.length.toLocaleString(locale())} ${items.length === 1 ? t('archived item') : t('archived items')} · ${formatBytes(totalBytes)}`
      : `${items.length.toLocaleString(locale())} archived item${items.length === 1 ? '' : 's'} · ${formatBytes(totalBytes)}`)
    : t('No archived items found');

  items.forEach(item => {
    const isVideo = String(item.media_type || '').startsWith('video/');
    const label = item.category === 'recordings' && item.subtype
      ? recordingSubtypeLabel(item.subtype)
      : title(item.category);
    const card = document.createElement('article');
    card.className = `archive-card${isVideo ? ' is-video' : ''}`;

    const preview = document.createElement(isVideo ? 'button' : 'a');
    preview.className = 'archive-preview';
    if (isVideo) {
      preview.type = 'button';
      preview.setAttribute('aria-label', `${t('Play')} ${item.filename}`);
      preview.addEventListener('click', () => openPlayer(item));
    } else {
      preview.href = `/media/${item.id}`;
      preview.target = '_blank';
      preview.rel = 'noopener';
      preview.setAttribute('aria-label', `${t('Open')} ${item.filename}`);
    }

    const fallback = document.createElement('span');
    fallback.className = 'archive-preview-fallback';
    fallback.textContent = isVideo ? '◫' : '{}';
    preview.append(fallback);

    if (item.thumbnail_url) {
      const image = document.createElement('img');
      image.src = item.thumbnail_url;
      image.alt = '';
      image.loading = 'lazy';
      image.decoding = 'async';
      image.addEventListener('error', () => image.remove());
      preview.append(image);
    }

    const typeChip = document.createElement('span');
    typeChip.className = `archive-type-chip ${item.subtype || item.category}`;
    typeChip.textContent = label;
    const sizeChip = document.createElement('span');
    sizeChip.className = 'archive-size-chip';
    sizeChip.textContent = formatBytes(item.size_bytes);
    preview.append(typeChip, sizeChip);

    if (isVideo) {
      const play = document.createElement('span');
      play.className = 'archive-play-action';
      const playIcon = document.createElement('i');
      playIcon.textContent = '▶';
      const playLabel = document.createElement('span');
      playLabel.textContent = t('Play recording');
      play.append(playIcon, playLabel);
      preview.append(play);
    }

    const content = document.createElement('div');
    content.className = 'archive-card-content';
    const recorded = document.createElement('h3');
    recorded.textContent = exactTime(item.source_timestamp || item.created_at);
    const filename = document.createElement('p');
    filename.className = 'archive-filename';
    filename.textContent = item.filename;
    filename.title = item.filename;

    const footer = document.createElement('div');
    footer.className = 'archive-card-footer';
    const identity = document.createElement('span');
    const identityDot = document.createElement('i');
    const identityName = document.createTextNode(title(item.vehicle));
    identity.append(identityDot, identityName);
    const download = document.createElement('a');
    download.className = 'archive-download';
    download.href = `/media/${item.id}`;
    download.download = item.filename;
    download.textContent = t(isVideo ? 'Download' : 'Open file');
    footer.append(identity, download);
    content.append(recorded, filename, footer);
    card.append(preview, content);
    grid.append(card);
  });
}

function normalizedCameraLayout(value) {
  const layout = String(value || '').trim().toLowerCase();
  if (layout === 'dashcam' || layout === 'single') return layout;
  return 'standard';
}

function announcePlayerCameraView() {
  const label = t(playerCameraLabels[state.playerCameraView] || playerCameraLabels.all);
  $('player-camera-status').textContent = `${t('Showing')}: ${label}`;
}

function setPlayerCameraView(view, { announce = true } = {}) {
  const target = state.playerCameraLayout === 'single' || !playerCameraViews.includes(view)
    ? 'all'
    : view;
  state.playerCameraView = target;
  const viewport = $('player-viewport');
  playerCameraViews.forEach(camera => viewport.classList.remove(`view-${camera}`));
  viewport.classList.add(`view-${target}`);
  document.querySelectorAll('[data-camera-view]').forEach(button => {
    const active = button.dataset.cameraView === target;
    button.classList.toggle('active', active);
    button.setAttribute('aria-pressed', String(active));
  });
  if (announce && $('player-dialog').open) announcePlayerCameraView();
}

function setPlayerCameraLayout(value) {
  state.playerCameraLayout = normalizedCameraLayout(value);
  const viewport = $('player-viewport');
  viewport.classList.remove('layout-standard', 'layout-dashcam', 'layout-single');
  viewport.classList.add(`layout-${state.playerCameraLayout}`);
  $('player-camera-selector').hidden = state.playerCameraLayout === 'single';
  setPlayerCameraView('all', { announce: false });
}

function formatPlayerTime(value) {
  const seconds = Number.isFinite(Number(value)) ? Math.max(0, Math.floor(Number(value))) : 0;
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const remainder = seconds % 60;
  return hours > 0
    ? `${hours}:${String(minutes).padStart(2, '0')}:${String(remainder).padStart(2, '0')}`
    : `${minutes}:${String(remainder).padStart(2, '0')}`;
}

function playerDurationAttribute(value) {
  const seconds = Number.isFinite(Number(value)) ? Math.max(0, Math.floor(Number(value))) : 0;
  return `PT${seconds}S`;
}

function updatePlayerTimeline() {
  const player = $('player');
  const duration = Number.isFinite(player.duration) ? Math.max(0, player.duration) : 0;
  const current = Number.isFinite(player.currentTime) ? Math.max(0, player.currentTime) : 0;
  const currentLabel = formatPlayerTime(current);
  const durationLabel = formatPlayerTime(duration);
  $('player-current-time').textContent = currentLabel;
  $('player-current-time').dateTime = playerDurationAttribute(current);
  $('player-duration').textContent = durationLabel;
  $('player-duration').dateTime = playerDurationAttribute(duration);
  const progress = $('player-progress');
  progress.disabled = duration <= 0;
  progress.max = String(duration || 0);
  progress.value = String(Math.min(current, duration || 0));
  progress.setAttribute('aria-valuetext', `${currentLabel} ${t('of')} ${durationLabel}`);
}

function playerIsFullscreen() {
  return (document.fullscreenElement || document.webkitFullscreenElement) === $('player-stage');
}

function updatePlayerControls() {
  const player = $('player');
  const playing = !player.paused && !player.ended;
  const playLabel = t(playing ? 'Pause' : 'Play');
  $('player-play').classList.toggle('is-playing', playing);
  $('player-play').setAttribute('aria-label', playLabel);
  $('player-play').title = playLabel;

  const muted = player.muted || player.volume === 0;
  const muteLabel = t(muted ? 'Unmute' : 'Mute');
  $('player-mute').classList.toggle('is-muted', muted);
  $('player-mute').setAttribute('aria-label', muteLabel);
  $('player-mute').title = muteLabel;

  const stage = $('player-stage');
  const fullscreen = playerIsFullscreen();
  const fullscreenLabel = t(fullscreen ? 'Exit fullscreen' : 'Enter fullscreen');
  const fullscreenButton = $('player-fullscreen');
  fullscreenButton.hidden = !(stage.requestFullscreen || stage.webkitRequestFullscreen);
  fullscreenButton.setAttribute('aria-label', fullscreenLabel);
  fullscreenButton.title = fullscreenLabel;
}

function togglePlayerPlayback() {
  const player = $('player');
  if (!player.currentSrc && !player.getAttribute('src')) return;
  if (player.paused || player.ended) {
    player.play().catch(() => updatePlayerControls());
  } else {
    player.pause();
  }
}

function togglePlayerMuted() {
  const player = $('player');
  player.muted = !player.muted;
  if (!player.muted && player.volume === 0) player.volume = 1;
  updatePlayerControls();
}

function togglePlayerFullscreen() {
  const stage = $('player-stage');
  if (playerIsFullscreen()) {
    const exit = document.exitFullscreen || document.webkitExitFullscreen;
    if (exit) {
      try {
        const result = exit.call(document);
        if (result?.catch) result.catch(() => {});
      } catch {}
    }
    return;
  }
  const enter = stage.requestFullscreen || stage.webkitRequestFullscreen;
  if (!enter) return;
  try {
    const result = enter.call(stage);
    if (result?.catch) result.catch(() => {});
  } catch {}
}

function openPlayer(item) {
  const label = recordingSubtypeLabel(item.subtype || item.category);
  const player = $('player');
  setPlayerCameraLayout(item.camera_layout);
  setPlayerCameraView('all', { announce: false });
  $('player-camera-status').textContent = '';
  $('player-viewport').style.removeProperty('aspect-ratio');
  $('player-kind').className = `item-tag ${item.subtype || ''}`;
  $('player-kind').textContent = label;
  $('player-title').textContent = label;
  $('player-filename').textContent = item.filename;
  $('player-recorded').textContent = exactTime(item.source_timestamp || item.created_at);
  $('player-vehicle').textContent = title(item.vehicle);
  $('player-size').textContent = formatBytes(item.size_bytes);
  $('player-integrity').textContent = `${String(item.sha256 || '').slice(0, 12)}…`;
  $('player-download').href = `/media/${item.id}`;
  $('player-download').download = item.filename;
  player.poster = item.thumbnail_url || '';
  player.src = `/media/${item.id}`;
  player.load();
  updatePlayerTimeline();
  updatePlayerControls();
  $('player-dialog').showModal();
  player.play().catch(() => updatePlayerControls());
}

function closePlayer() {
  const player = $('player');
  if (playerIsFullscreen()) {
    const exit = document.exitFullscreen || document.webkitExitFullscreen;
    if (exit) {
      try {
        const result = exit.call(document);
        if (result?.catch) result.catch(() => {});
      } catch {}
    }
  }
  player.pause();
  setPlayerCameraLayout('standard');
  setPlayerCameraView('all', { announce: false });
  $('player-camera-status').textContent = '';
  $('player-viewport').style.removeProperty('aspect-ratio');
  player.removeAttribute('src');
  player.removeAttribute('poster');
  player.load();
  updatePlayerTimeline();
  updatePlayerControls();
  if ($('player-dialog').open) $('player-dialog').close();
}

async function initialize() {
  try {
    const session = await api('/api/session');
    if (session.authenticated) {
      showApp();
      loadSettings();
    } else {
      showLogin(session.auth);
    }
  } catch {
    showLogin();
  }
}

$('login-form').addEventListener('submit', async event => {
  event.preventDefault();
  $('login-button').disabled = true;
  $('login-error').textContent = '';
  try {
    if (state.authMethod === 'local') {
      await api('/api/login', {
        method: 'POST',
        body: JSON.stringify({
          username: $('login-username').value,
          password: $('login-password').value,
        }),
      });
      $('login-password').value = '';
    } else {
      await api('/api/auth/verify-code', {
        method: 'POST',
        body: JSON.stringify({
          provider: state.authMethod,
          code: $('login-code').value,
        }),
      });
      $('login-code').value = '';
    }
    showApp();
    loadSettings();
  } catch (error) {
    $('login-error').textContent = error.message;
  } finally {
    $('login-button').disabled = false;
  }
});

$('request-code').addEventListener('click', async () => {
  $('request-code').disabled = true;
  $('login-error').textContent = '';
  try {
    const response = await api('/api/auth/request-code', {
      method: 'POST',
      body: JSON.stringify({ provider: state.authMethod }),
    });
    toast(t(response.message || 'One-time code sent'));
    $('login-code').focus();
  } catch (error) {
    $('login-error').textContent = error.message;
  } finally {
    $('request-code').disabled = false;
  }
});

$('logout-button').addEventListener('click', async () => {
  try { await api('/api/logout', { method: 'POST', body: '{}' }); } catch {}
  showLogin();
});

document.querySelectorAll('[data-view-target]').forEach(element => {
  element.addEventListener('click', event => {
    event.preventDefault();
    setView(element.dataset.viewTarget);
  });
});

$('menu-button').addEventListener('click', () => document.body.classList.toggle('nav-open'));
$('sync-now-top').addEventListener('click', runSync);
$('sync-now-hero').addEventListener('click', runSync);
$('refresh-overview').addEventListener('click', loadOverview);
$('refresh-library').addEventListener('click', loadLibrary);
$('library-category').addEventListener('change', () => {
  updateRecordingTypeFilterState();
  loadLibrary();
});
$('library-recording-type').addEventListener('change', loadLibrary);
let searchTimer;
$('library-search').addEventListener('input', () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(loadLibrary, 300);
});
$('schedule-mode').addEventListener('change', updateScheduleVisibility);
$('interface-language').addEventListener('change', () => {
  applyLanguage($('interface-language').value);
  $('settings-status').textContent = state.language === 'pt-BR'
    ? 'Idioma alterado. Salve as configurações para manter esta escolha.'
    : 'Language changed. Save settings to keep this choice.';
});
$('settings-form').addEventListener('submit', event => { event.preventDefault(); saveSettings(); });
$('save-settings-top').addEventListener('click', () => saveSettings());
$('test-connection').addEventListener('click', testConnection);

document.querySelectorAll('[data-camera-view]').forEach(button => {
  button.addEventListener('click', () => setPlayerCameraView(button.dataset.cameraView));
});
$('player-camera-selector').addEventListener('keydown', event => {
  const current = event.target.closest('[data-camera-view]');
  if (!current) return;
  const buttons = [...document.querySelectorAll('[data-camera-view]')];
  const index = buttons.indexOf(current);
  let nextIndex = index;
  if (event.key === 'ArrowRight' || event.key === 'ArrowDown') nextIndex = (index + 1) % buttons.length;
  else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') nextIndex = (index - 1 + buttons.length) % buttons.length;
  else if (event.key === 'Home') nextIndex = 0;
  else if (event.key === 'End') nextIndex = buttons.length - 1;
  else return;
  event.preventDefault();
  buttons[nextIndex].focus();
  setPlayerCameraView(buttons[nextIndex].dataset.cameraView);
});

$('player-play').addEventListener('click', togglePlayerPlayback);
$('player-mute').addEventListener('click', togglePlayerMuted);
$('player-fullscreen').addEventListener('click', togglePlayerFullscreen);
$('player-progress').addEventListener('input', event => {
  const player = $('player');
  const value = Number(event.target.value);
  if (!Number.isFinite(value) || !Number.isFinite(player.duration) || player.duration <= 0) return;
  player.currentTime = Math.max(0, Math.min(value, player.duration));
  updatePlayerTimeline();
});
$('player').addEventListener('click', togglePlayerPlayback);
$('player').addEventListener('keydown', event => {
  if (event.altKey || event.ctrlKey || event.metaKey) return;
  const key = event.key.toLowerCase();
  const player = $('player');
  if (key === ' ' || key === 'enter' || key === 'k') {
    event.preventDefault();
    togglePlayerPlayback();
  } else if (key === 'm') {
    event.preventDefault();
    togglePlayerMuted();
  } else if (key === 'f') {
    event.preventDefault();
    togglePlayerFullscreen();
  } else if (key === 'arrowleft') {
    event.preventDefault();
    player.currentTime = Math.max(0, player.currentTime - 5);
  } else if (key === 'arrowright' && Number.isFinite(player.duration)) {
    event.preventDefault();
    player.currentTime = Math.min(player.duration, player.currentTime + 5);
  }
});
$('player').addEventListener('loadedmetadata', () => {
  const player = $('player');
  if (player.videoWidth > 0 && player.videoHeight > 0) {
    $('player-viewport').style.aspectRatio = `${player.videoWidth} / ${player.videoHeight}`;
  }
  updatePlayerTimeline();
  updatePlayerControls();
});
['timeupdate', 'durationchange', 'emptied'].forEach(eventName => {
  $('player').addEventListener(eventName, updatePlayerTimeline);
});
['play', 'pause', 'ended', 'volumechange'].forEach(eventName => {
  $('player').addEventListener(eventName, updatePlayerControls);
});
document.addEventListener('fullscreenchange', updatePlayerControls);
document.addEventListener('webkitfullscreenchange', updatePlayerControls);

$('close-player').addEventListener('click', closePlayer);
$('player-dialog').addEventListener('click', event => {
  if (event.target === $('player-dialog')) closePlayer();
});
$('player-dialog').addEventListener('cancel', event => {
  event.preventDefault();
  closePlayer();
});

updateRecordingTypeFilterState();
applyLanguage(state.language, { rerender: false });
initialize();
