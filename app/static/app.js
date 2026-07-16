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
  'Stored media and metadata-only placeholders': 'Mídia armazenada e marcadores somente com metadados',
  'No archived items match these filters.': 'Nenhum item arquivado corresponde a estes filtros.',
  'Load more': 'Carregar mais',
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
  'Recording camera layout': 'Layout das câmeras de gravação',
  'Surveillance camera layout': 'Layout das câmeras de vigilância',
  'Automatic / standard': 'Automático / padrão',
  'Standard 2 × 2': 'Padrão 2 × 2',
  'Dashcam mosaic': 'Mosaico dashcam',
  'Used for ACC and Replay recordings when the clip does not report its layout.': 'Usado para gravações ACC e Replay quando o vídeo não informa o próprio layout.',
  'Used for Surveillance and Proximity recordings when the clip does not report its layout.': 'Usado para gravações de Vigilância e Proximidade quando o vídeo não informa o próprio layout.',
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
  'Local retention': 'Retenção local',
  'Remove older local archive copies by category and optionally limit total storage usage.': 'Remova cópias locais antigas por categoria e, opcionalmente, limite o uso total do armazenamento.',
  'Vehicle recordings stay untouched': 'As gravações do veículo permanecem intactas',
  'Retention deletes only local archive copies. It never deletes or changes recordings stored in the vehicle.': 'A retenção apaga somente cópias do arquivo local. Ela nunca apaga nem altera as gravações armazenadas no veículo.',
  'Saving settings applies enabled retention rules immediately to local files.': 'Salvar as configurações aplica imediatamente aos arquivos locais as regras de retenção ativadas.',
  'Retention by category': 'Retenção por categoria',
  'Items protected by “Keep the latest” are never deleted by age or by the storage limit.': 'Os itens protegidos por “Manter os mais recentes” nunca são apagados por prazo nem pelo limite de armazenamento.',
  'Age uses the original recording time when available, then falls back to the local archive time.': 'O prazo usa a data original da gravação quando disponível e, como alternativa, a data do arquivo local.',
  'Storage limit': 'Limite de armazenamento',
  'Limit archive storage usage': 'Limitar o uso do armazenamento pelo arquivo',
  'When disabled, the archive may use the whole available filesystem.': 'Quando desativado, o arquivo pode usar todo o espaço disponível no sistema de arquivos.',
  'Maximum archive size (GB)': 'Tamanho máximo do arquivo (GB)',
  'Archive filesystem capacity is not available yet.': 'A capacidade do sistema de arquivos ainda não está disponível.',
  'Local copies only': 'Somente cópias locais',
  'Delete local copies older than': 'Apagar cópias locais com mais de',
  'Retention value': 'Valor da retenção',
  'Retention unit': 'Unidade da retenção',
  'Keep the latest': 'Manter os mais recentes',
  'Protected item count': 'Quantidade de itens protegidos',
  'Archive filesystem capacity': 'Capacidade do sistema de arquivos',
  'The storage limit is disabled.': 'O limite de armazenamento está desativado.',
  'The configured storage limit is active.': 'O limite de armazenamento configurado está ativo.',
  'Surveillance severity': 'Severidade da vigilância',
  'These labels come from Overdrive and filter Surveillance and Proximity recordings. With none selected, severity filtering is disabled; recordings without a reported severity are kept.': 'Esses rótulos vêm do Overdrive e filtram gravações de Vigilância e Proximidade. Sem nenhuma opção marcada, o filtro de severidade fica desativado; gravações sem severidade informada são mantidas.',
  'Notice covers background or passing activity; Alert marks nearby or approaching activity; Critical marks the closest or strongest reported threat. This archive only filters the label reported by Overdrive.': 'Aviso cobre atividade de fundo ou de passagem; Alerta marca atividade próxima ou se aproximando; Crítico marca a ameaça mais próxima ou mais forte informada. Este arquivo apenas filtra o rótulo informado pelo Overdrive.',
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
  'Retention will run after the current synchronization.': 'A retenção será executada após a sincronização atual.',
  'The storage target could not be reached because the remaining data is protected or unmanaged.': 'Não foi possível atingir o limite de armazenamento porque os dados restantes estão protegidos ou não são gerenciados.',
  'Retention could not remove some local items.': 'A retenção não conseguiu remover alguns itens locais.',
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
  'Synchronization progress': 'Progresso da sincronização',
  'Stop synchronization': 'Parar sincronização',
  'Stopping…': 'Parando…',
  'Stop requested.': 'Parada solicitada.',
  'Synchronization stop requested.': 'Parada da sincronização solicitada.',
  'No synchronization is running.': 'Nenhuma sincronização está em execução.',
  'Synchronization stopped by user.': 'Sincronização interrompida pelo usuário.',
  'Known bytes': 'Bytes conhecidos',
  'Size unavailable for': 'Tamanho indisponível para',
  'queued item': 'item na fila',
  'queued items': 'itens na fila',
  'Play recording': 'Reproduzir gravação',
  'Download': 'Baixar',
  'Open file': 'Abrir arquivo',
  'No archived items found': 'Nenhum item arquivado encontrado',
  'Deleted locally': 'Apagado localmente',
  'Download again': 'Baixar novamente',
  'Restore queued': 'Restauração na fila',
  'Local cleanup pending': 'Limpeza local pendente',
  'Requesting…': 'Solicitando…',
  '0 B stored': '0 B armazenados',
  'on vehicle': 'no veículo',
  'Only metadata is kept. This placeholder disappears after a complete vehicle listing confirms the recording is no longer on the vehicle.': 'Somente os metadados são mantidos. Este marcador desaparece depois que uma listagem completa do veículo confirma que a gravação não está mais nele.',
  'Synchronization started to download the recording again.': 'A sincronização foi iniciada para baixar a gravação novamente.',
  'Restore queued for the next synchronization.': 'Restauração colocada na fila para a próxima sincronização.',
  'Local retention cleanup is still in progress. Try again shortly.': 'A limpeza da retenção local ainda está em andamento. Tente novamente em instantes.',
  'Protected from retention': 'Protegido contra retenção',
  'Use retention rules': 'Usar regras de retenção',
  'This removes the manual protection. Current retention rules may delete the local copy immediately. Continue?': 'Isso remove a proteção manual. As regras atuais de retenção podem apagar a cópia local imediatamente. Continuar?',
  'Releasing…': 'Liberando…',
  'Automatic retention is enabled again for this recording.': 'A retenção automática foi reativada para esta gravação.',
  'The current retention rules removed the local copy.': 'As regras atuais de retenção removeram a cópia local.',
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
  'item deleted locally': 'item apagado localmente',
  'items deleted locally': 'itens apagados localmente',
  'stored': 'armazenados',
  'new': 'novos',
  'success': 'sucesso',
  'failed': 'falhou',
  'partial': 'parcial',
  'skipped': 'ignorado',
  'running': 'em execução',
  'cancelled': 'cancelada',
  'item': 'item',
  'items': 'itens',
  'transferred': 'transferidos',
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
  libraryRequestId: 0,
  libraryAbortController: null,
  libraryNextOffset: 0,
  libraryHasMore: false,
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

const RETENTION_CATEGORIES = [
  ['recordings', 'Recordings'],
  ['trips', 'Trips'],
  ['charging', 'Charging'],
  ['automations', 'Automations'],
  ['key_mappings', 'Key mappings'],
  ['telemetry', 'Telemetry'],
  ['roadsense', 'RoadSense'],
  ['configuration', 'Configuration'],
];
const RETENTION_UNITS = ['minutes', 'hours', 'days'];
const GIB = 1024 ** 3;

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
  if ($('retention-storage-capacity')) updateRetentionStorageCapacity();
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
    cancelled: 'cancelled',
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

function renderRuns(runs, sync = {}) {
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
    const detailCopy = document.createElement('span');
    detailCopy.textContent = run.status === 'cancelled'
      ? t(run.message || 'Synchronization stopped by user.')
      : (run.message || '—');
    details.append(detailCopy);
    const isCurrentRun = Boolean(sync.active)
      && run.status === 'running'
      && String(run.id) === String(sync.run_id);
    if (isCurrentRun) {
      details.classList.add('run-details');
      detailCopy.textContent = t(sync.current || 'Synchronizing…');
      const stop = document.createElement('button');
      stop.type = 'button';
      stop.className = 'button danger small';
      stop.textContent = t(sync.stop_requested ? 'Stopping…' : 'Stop synchronization');
      stop.disabled = Boolean(sync.stop_requested);
      stop.addEventListener('click', () => stopSynchronization(stop));
      details.append(stop);
    }
    row.append(started, reason, result, added, transferred, details);
    body.append(row);
  });
}

function renderSyncProgress(sync) {
  const progress = $('sync-progress');
  const active = Boolean(sync.active);
  progress.classList.toggle('hidden', !active);
  if (!active) return;

  const done = Math.max(0, Number(sync.queue_bytes_done) || 0);
  const total = Math.max(0, Number(sync.queue_bytes_total) || 0);
  const unknownSizes = Math.max(0, Number(sync.queue_unknown_sizes) || 0);
  const hasUnknownSizes = unknownSizes > 0 || Boolean(sync.queue_bytes_indeterminate);
  const hasTotal = Number.isFinite(total) && total > 0 && !hasUnknownSizes;
  const stopping = Boolean(sync.stop_requested);
  const value = $('sync-progress-value');
  const bar = $('sync-progress-bar');
  const parts = [];

  progress.setAttribute('aria-label', t('Synchronization progress'));
  progress.setAttribute('aria-valuemin', '0');
  if (hasTotal) {
    const percent = Math.min(100, Math.max(0, Math.round((done / total) * 100)));
    value.textContent = stopping ? t('Stopping…') : `${percent}%`;
    bar.style.width = `${percent}%`;
    progress.classList.remove('indeterminate');
    progress.setAttribute('aria-valuemax', '100');
    progress.setAttribute('aria-valuenow', String(percent));
    progress.setAttribute('aria-valuetext', `${percent}% · ${formatBytes(done)} / ${formatBytes(total)}`);
    parts.push(`${formatBytes(done)} / ${formatBytes(total)}`);
  } else {
    value.textContent = t(stopping ? 'Stopping…' : 'Synchronizing…');
    bar.style.width = '';
    progress.classList.add('indeterminate');
    progress.removeAttribute('aria-valuemax');
    progress.removeAttribute('aria-valuenow');
    progress.setAttribute('aria-valuetext', value.textContent);
    if (total > 0) parts.push(`${t('Known bytes')}: ${formatBytes(done)} / ${formatBytes(total)}`);
    else if (done > 0) parts.push(`${formatBytes(done)} ${t('transferred')}`);
  }

  const itemsDone = Math.max(0, Number(sync.queue_items_done) || 0);
  const itemsTotal = Math.max(0, Number(sync.queue_items_total) || 0);
  if (itemsTotal > 0) {
    parts.push(state.language === 'pt-BR'
      ? `${itemsDone} de ${itemsTotal} ${t(itemsTotal === 1 ? 'item' : 'items')}`
      : `${itemsDone} of ${itemsTotal} ${itemsTotal === 1 ? 'item' : 'items'}`);
  } else if (itemsDone > 0) {
    parts.push(`${itemsDone} ${t(itemsDone === 1 ? 'item' : 'items')}`);
  }
  if (unknownSizes > 0) {
    parts.push(`${t('Size unavailable for')} ${unknownSizes} ${t(unknownSizes === 1 ? 'queued item' : 'queued items')}`);
  }
  if (sync.current) parts.push(t(sync.current));
  $('sync-progress-detail').textContent = parts.join(' · ');
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
  renderSyncProgress(sync);
  const chip = $('sync-chip');
  chip.className = `status-chip${active ? ' running' : ''}`;
  chip.querySelector('strong').textContent = active ? t(sync.current || 'Synchronizing') : t('Idle');
  $('sync-now-top').classList.toggle('hidden', active);
  [$('sync-now-top'), $('sync-now-hero')].forEach(button => {
    button.disabled = active;
    button.textContent = active ? t('Synchronizing…') : t(button.id === 'sync-now-hero' ? 'Start synchronization' : 'Sync now');
  });
  renderRuns(runs, sync);
  renderCategories(Array.isArray(stats.categories) ? stats.categories : []);
  updateRetentionStorageCapacity();
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

async function stopSynchronization(button) {
  button.disabled = true;
  button.textContent = t('Stopping…');
  try {
    const response = await api('/api/sync/stop', { method: 'POST', body: '{}' });
    toast(t(response.message || 'Stop requested.'));
    await loadOverview();
  } catch (error) {
    button.disabled = false;
    button.textContent = t('Stop synchronization');
    toast(t(error.message));
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

function buildRetentionControls() {
  const container = $('retention-category-options');
  container.replaceChildren();
  RETENTION_CATEGORIES.forEach(([category, label]) => {
    const row = document.createElement('div');
    row.className = 'retention-category';
    row.dataset.retentionCategory = category;

    const heading = document.createElement('div');
    heading.className = 'retention-category-heading';
    const name = document.createElement('strong');
    name.textContent = label;
    const localOnly = document.createElement('small');
    localOnly.textContent = 'Local copies only';
    heading.append(name, localOnly);

    const rules = document.createElement('div');
    rules.className = 'retention-rules';

    const ageRule = document.createElement('div');
    ageRule.className = 'retention-rule';
    const ageToggle = document.createElement('label');
    ageToggle.className = 'retention-rule-copy';
    const ageEnabled = document.createElement('input');
    ageEnabled.id = `retention-${category}-enabled`;
    ageEnabled.className = 'retention-rule-enabled';
    ageEnabled.type = 'checkbox';
    const ageCopy = document.createElement('span');
    ageCopy.textContent = 'Delete local copies older than';
    ageToggle.append(ageEnabled, ageCopy);
    const ageValue = document.createElement('input');
    ageValue.id = `retention-${category}-value`;
    ageValue.className = 'retention-rule-value';
    ageValue.type = 'number';
    ageValue.min = '1';
    ageValue.max = '1000000';
    ageValue.step = '1';
    ageValue.value = '30';
    ageValue.inputMode = 'numeric';
    ageValue.setAttribute('aria-label', 'Retention value');
    const ageUnit = document.createElement('select');
    ageUnit.id = `retention-${category}-unit`;
    ageUnit.className = 'retention-rule-unit';
    ageUnit.setAttribute('aria-label', 'Retention unit');
    RETENTION_UNITS.forEach(unit => {
      const option = document.createElement('option');
      option.value = unit;
      option.textContent = unit[0].toUpperCase() + unit.slice(1);
      ageUnit.append(option);
    });
    ageUnit.value = 'days';
    ageRule.append(ageToggle, ageValue, ageUnit);

    const latestRule = document.createElement('div');
    latestRule.className = 'retention-rule';
    const latestToggle = document.createElement('label');
    latestToggle.className = 'retention-rule-copy';
    const latestEnabled = document.createElement('input');
    latestEnabled.id = `retention-${category}-keep-latest-enabled`;
    latestEnabled.className = 'retention-latest-enabled';
    latestEnabled.type = 'checkbox';
    const latestCopy = document.createElement('span');
    latestCopy.textContent = 'Keep the latest';
    latestToggle.append(latestEnabled, latestCopy);
    const latestCount = document.createElement('input');
    latestCount.id = `retention-${category}-keep-latest-count`;
    latestCount.className = 'retention-latest-count';
    latestCount.type = 'number';
    latestCount.min = '1';
    latestCount.max = '1000000';
    latestCount.step = '1';
    latestCount.value = '1';
    latestCount.inputMode = 'numeric';
    latestCount.setAttribute('aria-label', 'Protected item count');
    const items = document.createElement('span');
    items.textContent = 'items';
    latestRule.append(latestToggle, latestCount, items);

    rules.append(ageRule, latestRule);
    row.append(heading, rules);
    container.append(row);
  });
  updateRetentionControlState();
}

function updateRetentionControlState() {
  document.querySelectorAll('[data-retention-category]').forEach(row => {
    const ageEnabled = row.querySelector('.retention-rule-enabled').checked;
    row.querySelector('.retention-rule-value').disabled = !ageEnabled;
    row.querySelector('.retention-rule-unit').disabled = !ageEnabled;
    const latestEnabled = row.querySelector('.retention-latest-enabled').checked;
    row.querySelector('.retention-latest-count').disabled = !latestEnabled;
  });
  $('retention-storage-gb').disabled = !$('retention-storage-enabled').checked;
}

function archiveStorageCapacityBytes() {
  const overview = state.lastOverview || {};
  const settings = state.settings || {};
  const candidates = [
    overview.storage_capacity_bytes,
    overview.storage?.storage_capacity_bytes,
    overview.stats?.storage_capacity_bytes,
    settings.runtime?.storage_capacity_bytes,
    settings.runtime?.storage?.storage_capacity_bytes,
    settings.storage?.storage_capacity_bytes,
  ];
  const capacity = candidates.map(Number).find(value => Number.isFinite(value) && value > 0);
  return capacity || 0;
}

function updateRetentionStorageCapacity({ initializeValue = false, configuredMaxBytes = 0 } = {}) {
  const input = $('retention-storage-gb');
  const enabled = $('retention-storage-enabled').checked;
  const capacity = archiveStorageCapacityBytes();
  let defaultMaximumGb = 1;
  if (capacity > 0) {
    const capacityGb = capacity / GIB;
    const inputMaximum = Math.floor(capacityGb * 1000) / 1000 || capacityGb;
    defaultMaximumGb = inputMaximum;
    input.max = String(inputMaximum);
    if (initializeValue) {
      input.value = Number(configuredMaxBytes) > 0
        ? String(Number((Number(configuredMaxBytes) / GIB).toFixed(3)))
        : '';
    }
  } else {
    input.removeAttribute('max');
    if (initializeValue) {
      input.value = Number(configuredMaxBytes) > 0
        ? String(Number((Number(configuredMaxBytes) / GIB).toFixed(3)))
        : '';
    }
  }
  if (enabled && !(Number(input.value) > 0)) input.value = String(defaultMaximumGb);
  input.disabled = !enabled;
  input.required = enabled;
  const capacityText = capacity > 0
    ? `${t('Archive filesystem capacity')}: ${formatBytes(capacity)}.`
    : t('Archive filesystem capacity is not available yet.');
  const policyText = enabled
    ? t('The configured storage limit is active.')
    : t('When disabled, the archive may use the whole available filesystem.');
  $('retention-storage-capacity').textContent = `${capacityText} ${policyText}`;
}

function populateRetentionSettings(settings) {
  const retention = settings.retention || {};
  const categories = retention.categories || {};
  RETENTION_CATEGORIES.forEach(([category]) => {
    const policy = categories[category] || {};
    $(`retention-${category}-enabled`).checked = Boolean(policy.enabled);
    $(`retention-${category}-value`).value = Number(policy.value) > 0 ? String(policy.value) : '30';
    $(`retention-${category}-unit`).value = RETENTION_UNITS.includes(policy.unit) ? policy.unit : 'days';
    $(`retention-${category}-keep-latest-enabled`).checked = Boolean(policy.keep_latest_enabled);
    $(`retention-${category}-keep-latest-count`).value = Number(policy.keep_latest_count) > 0
      ? String(policy.keep_latest_count)
      : '1';
  });
  const storageLimit = retention.storage_limit || {};
  $('retention-storage-enabled').checked = Boolean(storageLimit.enabled);
  updateRetentionControlState();
  updateRetentionStorageCapacity({
    initializeValue: true,
    configuredMaxBytes: Number(storageLimit.max_bytes) || 0,
  });
}

function retentionSettingsPayload() {
  const categories = {};
  RETENTION_CATEGORIES.forEach(([category]) => {
    categories[category] = {
      enabled: $(`retention-${category}-enabled`).checked,
      value: Number($(`retention-${category}-value`).value) || 1,
      unit: $(`retention-${category}-unit`).value,
      keep_latest_enabled: $(`retention-${category}-keep-latest-enabled`).checked,
      keep_latest_count: Number($(`retention-${category}-keep-latest-count`).value) || 1,
    };
  });
  return {
    categories,
    storage_limit: {
      enabled: $('retention-storage-enabled').checked,
      max_bytes: Math.round(Math.max(0, Number($('retention-storage-gb').value) || 0) * GIB),
    },
  };
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
  $('recording-layout').value = ['standard', 'dashcam'].includes(vehicle.recording_layout)
    ? vehicle.recording_layout
    : '';
  $('surveillance-layout').value = ['standard', 'dashcam'].includes(vehicle.surveillance_layout)
    ? vehicle.surveillance_layout
    : '';
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
  populateRetentionSettings(settings);
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
      recording_layout: $('recording-layout').value,
      surveillance_layout: $('surveillance-layout').value,
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
    retention: retentionSettingsPayload(),
  };
}

function retentionResultMessage(result) {
  if (!result) return t('Settings saved');
  if (result.status === 'deferred') {
    return `${t('Settings saved')} · ${t('Retention will run after the current synchronization.')}`;
  }
  if (result.limit_satisfied === false) {
    return `${t('Settings saved')} · ${t('The storage target could not be reached because the remaining data is protected or unmanaged.')}`;
  }
  if (result.status === 'partial' || (Number(result.error_count) || 0) > 0) {
    return `${t('Settings saved')} · ${t('Retention could not remove some local items.')}`;
  }
  const removed = Number(result.deleted_items) || 0;
  if (!removed) return t('Settings saved');
  return state.language === 'pt-BR'
    ? `${t('Settings saved')} · retenção removeu ${removed.toLocaleString(locale())} ${removed === 1 ? 'item local' : 'itens locais'}.`
    : `${t('Settings saved')} · retention removed ${removed.toLocaleString(locale())} local item${removed === 1 ? '' : 's'}.`;
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
    const resultMessage = retentionResultMessage(response.retention);
    $('settings-status').textContent = resultMessage;
    if (showMessage) toast(resultMessage);
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

async function loadLibrary({ append = false } = {}) {
  updateRecordingTypeFilterState();
  const requestId = ++state.libraryRequestId;
  if (state.libraryAbortController) state.libraryAbortController.abort();
  const controller = new AbortController();
  state.libraryAbortController = controller;
  const loadMore = $('library-load-more');
  if (!append) {
    state.libraryNextOffset = 0;
    state.libraryHasMore = false;
    loadMore.classList.add('hidden');
  }
  loadMore.disabled = true;
  $('library-grid').setAttribute('aria-busy', 'true');
  const params = new URLSearchParams();
  if ($('library-category').value) params.set('category', $('library-category').value);
  if ($('library-recording-type').value) params.set('subtype', $('library-recording-type').value);
  if ($('library-search').value.trim()) params.set('q', $('library-search').value.trim());
  params.set('limit', '100');
  params.set('offset', String(append ? state.libraryNextOffset : 0));
  try {
    const data = await api(`/api/items?${params}`, { signal: controller.signal });
    if (requestId !== state.libraryRequestId) return;
    renderRecordingTypeFilter(data.recording_types || []);
    const pageItems = Array.isArray(data.items) ? data.items : [];
    const items = append
      ? [...(state.lastLibraryItems || []), ...pageItems]
      : pageItems;
    state.libraryHasMore = Boolean(data.has_more);
    const nextOffset = Number(data.next_offset);
    state.libraryNextOffset = data.next_offset !== null && Number.isInteger(nextOffset) && nextOffset >= 0
      ? nextOffset
      : items.length;
    renderLibrary(items);
    loadMore.classList.toggle('hidden', !state.libraryHasMore);
  } catch (error) {
    if (error.name === 'AbortError') return;
    toast(error.message);
  } finally {
    if (requestId !== state.libraryRequestId) return;
    state.libraryAbortController = null;
    $('library-grid').setAttribute('aria-busy', 'false');
    loadMore.disabled = false;
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

async function requestRecordingRestore(item, button) {
  const restoreKey = String(item.restore_key || item.source_key || '');
  item.restore_requested = true;
  button.disabled = true;
  button.textContent = t('Requesting…');
  try {
    const response = await api('/api/recordings/restore', {
      method: 'POST',
      body: JSON.stringify({ source_key: restoreKey }),
    });
    item.restore_requested = true;
    button.textContent = t('Restore queued');
    const started = response.sync_started === true
      || response.started === true
      || response.sync?.started === true
      || response.status === 'started';
    toast(t(started
      ? 'Synchronization started to download the recording again.'
      : 'Restore queued for the next synchronization.'));
    await Promise.all([loadOverview(), loadLibrary()]);
  } catch (error) {
    item.restore_requested = false;
    button.disabled = false;
    button.textContent = t('Download again');
    toast(t(error.message));
  }
}

async function releaseRecordingRetention(item, button) {
  if (!window.confirm(t('This removes the manual protection. Current retention rules may delete the local copy immediately. Continue?'))) return;
  button.disabled = true;
  button.textContent = t('Releasing…');
  try {
    const response = await api('/api/recordings/release-retention', {
      method: 'POST',
      body: JSON.stringify({ item_id: item.id }),
    });
    const removed = response.item_deleted === true;
    toast(t(removed
      ? 'The current retention rules removed the local copy.'
      : 'Automatic retention is enabled again for this recording.'));
    await Promise.all([loadOverview(), loadLibrary()]);
  } catch (error) {
    button.disabled = false;
    button.textContent = t('Use retention rules');
    toast(t(error.message));
  }
}

function renderDeletedLocalCard(item, label, grid) {
  const card = document.createElement('article');
  card.className = 'archive-card deleted-local';

  const preview = document.createElement('div');
  preview.className = 'archive-preview deleted-local-preview';
  preview.setAttribute('role', 'img');
  preview.setAttribute('aria-label', `${t('Deleted locally')}: ${item.filename}`);

  const marker = document.createElement('span');
  marker.className = 'archive-deleted-marker';
  const markerIcon = document.createElement('i');
  markerIcon.textContent = '↻';
  const markerTitle = document.createElement('strong');
  markerTitle.textContent = t('Deleted locally');
  const markerSize = document.createElement('small');
  const remoteSize = Number(item.remote_size_bytes) || 0;
  markerSize.textContent = remoteSize > 0
    ? `${t('0 B stored')} · ${formatBytes(remoteSize)} ${t('on vehicle')}`
    : t('0 B stored');
  marker.append(markerIcon, markerTitle, markerSize);

  const typeChip = document.createElement('span');
  typeChip.className = `archive-type-chip ${item.subtype || item.category}`;
  typeChip.textContent = label;
  const sizeChip = document.createElement('span');
  sizeChip.className = 'archive-size-chip deleted-local-size';
  sizeChip.textContent = t('0 B stored');
  preview.append(marker, typeChip, sizeChip);

  const content = document.createElement('div');
  content.className = 'archive-card-content';
  const recorded = document.createElement('h3');
  recorded.textContent = exactTime(item.source_timestamp || item.created_at);
  const filename = document.createElement('p');
  filename.className = 'archive-filename';
  filename.textContent = item.filename;
  filename.title = item.filename;
  const explanation = document.createElement('p');
  explanation.className = 'archive-placeholder-note';
  explanation.textContent = t('Only metadata is kept. This placeholder disappears after a complete vehicle listing confirms the recording is no longer on the vehicle.');

  const footer = document.createElement('div');
  footer.className = 'archive-card-footer';
  const identity = document.createElement('span');
  const identityDot = document.createElement('i');
  const identityName = document.createTextNode(item.vehicle ? title(item.vehicle) : t('Vehicle'));
  identity.append(identityDot, identityName);
  const restore = document.createElement('button');
  restore.type = 'button';
  restore.className = 'button secondary small archive-restore';
  restore.disabled = Boolean(item.restore_requested || item.cleanup_pending);
  restore.textContent = t(item.cleanup_pending
    ? 'Local cleanup pending'
    : item.restore_requested ? 'Restore queued' : 'Download again');
  restore.addEventListener('click', () => requestRecordingRestore(item, restore));
  footer.append(identity, restore);
  content.append(recorded, filename, explanation, footer);
  card.append(preview, content);
  grid.append(card);
}

function renderLibrary(items) {
  state.lastLibraryItems = items;
  const grid = $('library-grid');
  grid.replaceChildren();
  grid.setAttribute('aria-busy', 'false');
  $('library-empty').classList.toggle('hidden', items.length > 0);
  const archivedItems = items.filter(item => !item.deleted_local);
  const deletedLocalItems = items.filter(item => Boolean(item.deleted_local));
  const totalBytes = archivedItems.reduce((total, item) => total + (Number(item.size_bytes) || 0), 0);
  const archivedSummary = state.language === 'pt-BR'
    ? `${archivedItems.length.toLocaleString(locale())} ${t(archivedItems.length === 1 ? 'archived item' : 'archived items')}`
    : `${archivedItems.length.toLocaleString(locale())} archived item${archivedItems.length === 1 ? '' : 's'}`;
  const deletedSummary = `${deletedLocalItems.length.toLocaleString(locale())} ${t(deletedLocalItems.length === 1 ? 'item deleted locally' : 'items deleted locally')}`;
  $('library-summary').textContent = items.length
    ? `${archivedSummary} · ${deletedSummary} · ${formatBytes(totalBytes)} ${t('stored')}`
    : t('No archived items found');
  $('library-view-note-copy').textContent = t(deletedLocalItems.length
    ? 'Stored media and metadata-only placeholders'
    : 'Private previews from your archive');
  $('library-view-note-copy').parentElement.classList.toggle('has-placeholders', deletedLocalItems.length > 0);

  items.forEach(item => {
    const isVideo = String(item.media_type || '').startsWith('video/');
    const label = item.category === 'recordings' && item.subtype
      ? recordingSubtypeLabel(item.subtype)
      : labelFor(item.category);
    if (item.deleted_local) {
      renderDeletedLocalCard(item, label, grid);
      return;
    }
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
    const actions = document.createElement('div');
    actions.className = 'archive-card-actions';
    if (item.retention_protected) {
      const release = document.createElement('button');
      release.type = 'button';
      release.className = 'archive-retention-release';
      release.title = t('Protected from retention');
      release.textContent = t('Use retention rules');
      release.addEventListener('click', () => releaseRecordingRetention(item, release));
      actions.append(release);
    }
    actions.append(download);
    footer.append(identity, actions);
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
$('refresh-library').addEventListener('click', () => loadLibrary());
$('library-load-more').addEventListener('click', () => loadLibrary({ append: true }));
$('library-category').addEventListener('change', () => {
  updateRecordingTypeFilterState();
  loadLibrary();
});
$('library-recording-type').addEventListener('change', () => loadLibrary());
let searchTimer;
$('library-search').addEventListener('input', () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(loadLibrary, 300);
});
$('schedule-mode').addEventListener('change', updateScheduleVisibility);
$('retention-category-options').addEventListener('change', updateRetentionControlState);
$('retention-storage-enabled').addEventListener('change', () => {
  updateRetentionControlState();
  updateRetentionStorageCapacity();
});
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

buildRetentionControls();
updateRecordingTypeFilterState();
applyLanguage(state.language, { rerender: false });
initialize();
