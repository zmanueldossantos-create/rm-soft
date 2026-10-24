; Saved as UTF-8 WITH BOM (the accents of the screens).
; RM SOFT - the Windows installer RMSOFT-Setup-<versão>.exe (Inno Setup 6). Not compiled by hand: fabricar_setup.ps1
; prepares the package (Pacote) and calls ISCC with /DVersao /DPacote /DSaida.
;
;   C:\Program Files\RMSOFT       the program: servidor\ (rmsoft-servidor.exe), ecras\, pgsql\, servico\, instalacao\
;   C:\ProgramData\RMSOFT         the data: .env, base\ (PostgreSQL), uploads\, logs\ - kept by an update or an uninstall
;
; First installation: 3 pages (port, copies' folder, SUPER_ADMIN account), then instalacao\configurar.ps1.
; Update (C:\ProgramData\RMSOFT\.env exists): no question; parar.ps1 first (copy of the database, services stopped),
; then the files, then configurar.ps1 (database brought to the new version, services started again).

#ifndef Versao
  #define Versao "1.0.0"
#endif
#ifndef Pacote
  #error "Pacote em falta: use fabricar_setup.ps1"
#endif
#ifndef Saida
  #define Saida "saida"
#endif

[Setup]
AppId={{8F3C2A71-5B4E-4D2A-9C61-7E0B3F9A1D52}
AppName=RM SOFT
AppVersion={#Versao}
AppVerName=RM SOFT {#Versao}
AppPublisher=RM SOFT
VersionInfoVersion={#Versao}
DefaultDirName={autopf}\RMSOFT
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=no
UsePreviousAppDir=yes
OutputDir={#Saida}
OutputBaseFilename=RMSOFT-Setup-{#Versao}
SetupIconFile={#Pacote}\rmsoft.ico
UninstallDisplayIcon={app}\rmsoft.ico
UninstallDisplayName=RM SOFT
Compression=lzma2/max
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
MinVersion=10.0
WizardStyle=modern
CloseApplications=no
RestartApplications=no
SetupLogging=yes

[Languages]
Name: "pt"; MessagesFile: "compiler:Languages\Portuguese.isl"

[InstallDelete]
; the previous version's program, replaced as a whole (the data are in ProgramData, never here)
Type: filesandordirs; Name: "{app}\servidor"
Type: filesandordirs; Name: "{app}\ecras"
Type: filesandordirs; Name: "{app}\pgsql"

[Files]
Source: "{#Pacote}\servidor\*"; DestDir: "{app}\servidor"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#Pacote}\ecras\*"; DestDir: "{app}\ecras"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#Pacote}\pgsql\*"; DestDir: "{app}\pgsql"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#Pacote}\servico\*"; DestDir: "{app}\servico"; Flags: ignoreversion
Source: "{#Pacote}\instalacao\*"; DestDir: "{app}\instalacao"; Flags: ignoreversion
Source: "{#Pacote}\rmsoft.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#Pacote}\vc_redist.x64.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall
Source: "{#Pacote}\parar.ps1"; Flags: dontcopy

[INI]
Filename: "{app}\RM SOFT.url"; Section: "InternetShortcut"; Key: "URL"; String: "{code:LocalAddress}"
Filename: "{app}\RM SOFT.url"; Section: "InternetShortcut"; Key: "IconFile"; String: "{app}\rmsoft.ico"
Filename: "{app}\RM SOFT.url"; Section: "InternetShortcut"; Key: "IconIndex"; String: "0"

[Icons]
Name: "{commondesktop}\RM SOFT"; Filename: "{app}\RM SOFT.url"; IconFilename: "{app}\rmsoft.ico"
Name: "{commonprograms}\RM SOFT\RM SOFT"; Filename: "{app}\RM SOFT.url"; IconFilename: "{app}\rmsoft.ico"
Name: "{commonprograms}\RM SOFT\Desinstalar o RM SOFT"; Filename: "{uninstallexe}"

[Run]
Filename: "{code:LocalAddress}"; Description: "Abrir o RM SOFT"; Flags: postinstall shellexec nowait skipifsilent

[UninstallRun]
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\instalacao\remover.ps1"""; Flags: runhidden waituntilterminated; RunOnceId: "RemoverServicos"

[UninstallDelete]
Type: files; Name: "{app}\RM SOFT.url"
Type: files; Name: "{app}\servico\rmsoft-servico.xml"
Type: files; Name: "{app}\servico\*.log"

[Messages]
FinishedHeadingLabel=O RM SOFT está instalado

[Code]
var
  PortPage: TInputQueryWizardPage;
  CopiasPage: TInputDirWizardPage;
  AdminPage: TInputQueryWizardPage;
  Upgrade: Boolean;
  Summary: String;

function DataDir: String;
begin
  Result := ExpandConstant('{commonappdata}\RMSOFT');
end;

function InitializeSetup: Boolean;
begin
  Upgrade := FileExists(DataDir + '\.env');  { already installed on this server: an update, no question }
  Result := True;
end;

procedure InitializeWizard;
begin
  PortPage := CreateInputQueryPage(wpWelcome, 'Rede', 'A porta do RM SOFT',
    'Os postos da loja (caixa, escritório) abrem o RM SOFT no Chrome com o nome deste servidor. ' +
    'Deixe 80, salvo se outro programa deste servidor já a usa (então, por exemplo, 8080).');
  PortPage.Add('Porta:', False);
  PortPage.Values[0] := '80';

  CopiasPage := CreateInputDirPage(PortPage.ID, 'Cópias de segurança', 'Onde guardar as cópias?',
    'De preferência um disco externo ou uma pasta de rede - nunca só o disco deste servidor. ' +
    'Pode ser mudado mais tarde em Definições da Empresa.', False, '');
  CopiasPage.Add('Pasta das cópias:');
  CopiasPage.Values[0] := DataDir + '\copias';

  AdminPage := CreateInputQueryPage(CopiasPage.ID, 'Conta RM SOFT', 'A conta SUPER_ADMIN deste servidor',
    'A conta do técnico RM SOFT: cria ou restaura a empresa e importa a licença. ' +
    'Telefone no formato internacional, por exemplo +244923000000.');
  AdminPage.Add('Nome completo:', False);
  AdminPage.Add('Telefone:', False);
  AdminPage.Add('Palavra-passe (mínimo 8 caracteres):', True);
  AdminPage.Add('Repetir a palavra-passe:', True);
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := Upgrade and ((PageID = PortPage.ID) or (PageID = CopiasPage.ID) or (PageID = AdminPage.ID));
end;

function CleanPhone(S: String): String;
begin
  Result := Trim(S);
  StringChangeEx(Result, ' ', '', True);
end;

function ValidPhone(S: String): Boolean;
var
  I: Integer;
begin
  Result := (Length(S) >= 10) and (Copy(S, 1, 1) = '+');
  if Result then
    for I := 2 to Length(S) do
      if (S[I] < '0') or (S[I] > '9') then
        Result := False;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Port: Integer;
begin
  Result := True;
  if CurPageID = PortPage.ID then begin
    Port := StrToIntDef(Trim(PortPage.Values[0]), 0);
    if (Port < 1) or (Port > 65535) then begin
      MsgBox('Porta inválida: um número entre 1 e 65535 (normalmente 80).', mbError, MB_OK);
      Result := False;
    end;
  end else if CurPageID = CopiasPage.ID then begin
    if Trim(CopiasPage.Values[0]) = '' then begin
      MsgBox('Escolha a pasta das cópias.', mbError, MB_OK);
      Result := False;
    end;
  end else if CurPageID = AdminPage.ID then begin
    if Trim(AdminPage.Values[0]) = '' then begin
      MsgBox('Escreva o nome completo.', mbError, MB_OK);
      Result := False;
    end else if not ValidPhone(CleanPhone(AdminPage.Values[1])) then begin
      MsgBox('Telefone inválido: formato internacional, por exemplo +244923000000.', mbError, MB_OK);
      Result := False;
    end else if Length(AdminPage.Values[2]) < 8 then begin
      MsgBox('A palavra-passe tem de ter pelo menos 8 caracteres.', mbError, MB_OK);
      Result := False;
    end else if AdminPage.Values[2] <> AdminPage.Values[3] then begin
      MsgBox('As duas palavras-passe não coincidem.', mbError, MB_OK);
      Result := False;
    end;
  end;
end;

{ The port: the page's at the first installation, the .env's at an update }
function CurrentPort: String;
var
  Lines: TArrayOfString;
  I: Integer;
begin
  Result := '80';
  if not Upgrade then
    Result := Trim(PortPage.Values[0])
  else if LoadStringsFromFile(DataDir + '\.env', Lines) then
    for I := 0 to GetArrayLength(Lines) - 1 do
      if Pos('RMSOFT_PORT=', Lines[I]) = 1 then
        Result := Trim(Copy(Lines[I], 13, 10));
end;

function LocalAddress(Param: String): String;
begin
  Result := 'http://localhost';
  if CurrentPort <> '80' then
    Result := Result + ':' + CurrentPort;
end;

function PowerShell(Script, Arguments: String; var Code: Integer): Boolean;
begin
  Result := Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
    '-NoProfile -ExecutionPolicy Bypass -File "' + Script + '" ' + Arguments, '', SW_HIDE, ewWaitUntilTerminated, Code);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Code: Integer;
begin
  Result := '';
  if Upgrade and FileExists(ExpandConstant('{app}\servidor\rmsoft-servidor.exe')) then begin
    ExtractTemporaryFile('parar.ps1');
    if not PowerShell(ExpandConstant('{tmp}\parar.ps1'), '-App "' + ExpandConstant('{app}') + '"', Code) or (Code <> 0) then
      Result := 'Não foi possível copiar a base de dados antes da atualização: nada foi mudado. ' +
        'Veja ' + DataDir + '\logs\instalacao.log';
  end;
end;

procedure Configure;
var
  Answers: TArrayOfString;
  AnswersFile, Arguments: String;
  Code: Integer;
  Lines: TArrayOfString;
  I: Integer;
begin
  WizardForm.StatusLabel.Caption := 'A configurar a base de dados e os serviços (alguns minutos)...';
  WizardForm.FilenameLabel.Caption := '';
  WizardForm.ProgressGauge.Style := npbstMarquee;

  { The Visual C++ runtime PostgreSQL needs: 1638 = a newer one is already there, 3010 = installed, restart later }
  Exec(ExpandConstant('{tmp}\vc_redist.x64.exe'), '/install /quiet /norestart', '', SW_HIDE, ewWaitUntilTerminated, Code);
  if (Code <> 0) and (Code <> 1638) and (Code <> 3010) and (Code <> 1641) then
    Log('vc_redist: código ' + IntToStr(Code));

  Arguments := '-App "' + ExpandConstant('{app}') + '"';
  if not Upgrade then begin
    AnswersFile := ExpandConstant('{tmp}\respostas.txt');
    SetArrayLength(Answers, 6);
    Answers[0] := 'PORTA=' + Trim(PortPage.Values[0]);
    Answers[1] := 'COPIAS=' + Trim(CopiasPage.Values[0]);
    Answers[2] := 'ADMIN_NOME=' + Trim(AdminPage.Values[0]);
    Answers[3] := 'ADMIN_TELEFONE=' + CleanPhone(AdminPage.Values[1]);
    Answers[4] := 'ADMIN_SENHA=' + AdminPage.Values[2];
    Answers[5] := '';
    SaveStringsToUTF8File(AnswersFile, Answers, False);
    Arguments := Arguments + ' -Respostas "' + AnswersFile + '"';
  end;

  if not PowerShell(ExpandConstant('{app}\instalacao\configurar.ps1'), Arguments, Code) or (Code <> 0) then begin
    Summary := 'A configuração NÃO terminou.' + #13#10#13#10 +
      'Veja o relatório ' + DataDir + '\logs\instalacao.log' + #13#10 +
      'Depois de corrigir, execute de novo o RMSOFT-Setup.exe (os dados ficam).';
    MsgBox(Summary, mbCriticalError, MB_OK);
  end else if LoadStringsFromFile(DataDir + '\resumo_instalacao.txt', Lines) then begin
    Summary := '';
    for I := 0 to GetArrayLength(Lines) - 1 do
      Summary := Summary + Lines[I] + #13#10;
  end;
  if AnswersFile <> '' then
    DeleteFile(AnswersFile);  { configurar.ps1 deletes it already: the SUPER_ADMIN password never stays on the disk }
  WizardForm.ProgressGauge.Style := npbstNormal;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    Configure;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if (CurPageID = wpFinished) and (Summary <> '') then
    WizardForm.FinishedLabel.Caption := Summary;
end;
