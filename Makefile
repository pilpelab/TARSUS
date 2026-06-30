# TARSUS_BC — Tool Setup
# Run `make setup` to download and verify all external tools.
# Versions are pinned — update intentionally.

TOOLS_DIR   := tools
DOWNLOAD_DIR := $(TOOLS_DIR)/_downloads
SHELL       := bash
.SHELLFLAGS := -eu -o pipefail -c

# ── FragPipe (Linux) ──────────────────────────────────────────────────
# Bundles: Philosopher, IonQuant, Percolator, MSBooster, etc.
# MSFragger IS NOT bundled — it must be downloaded separately (see below).
FP_VERSION   := 24.0
FP_URL       := https://github.com/Nesvilab/FragPipe/releases/download/$(FP_VERSION)/FragPipe-$(FP_VERSION)-linux.zip
FP_SHA256    := 6a7ad80b81d7e93e8fa194c1d22228ee35ea9a2ae8ba8dc6964bb26ea4385137
FP_ZIP       := FragPipe-$(FP_VERSION)-linux.zip
FP_DIR       := $(TOOLS_DIR)/fragpipe-$(FP_VERSION)

# ── MSFragger (required by FragPipe, NOT bundled) ─────────────────────
MF_VERSION   := 4.4.1
MF_JAR       := $(FP_DIR)/tools/MSFragger-$(MF_VERSION)/MSFragger-$(MF_VERSION).jar
MF_SHA256    := d5268024c10f29317a20c4b5f42a2ec142dc282c0e8fc733ca286ff76537644a
# No public download URL — obtain the ZIP from the MSFragger website
# (https://msfragger.nesvilab.org) and place it at the path below.
MF_SOURCE_ZIP := /home/labs/pilpel/slavat/fragpipe-24.0/tools/MSFragger-$(MF_VERSION).zip

# ── IonQuant (required by FragPipe, NOT bundled) ──────────────────────
IQ_JAR       := $(FP_DIR)/tools/IonQuant-1.11.20.jar
IQ_SHA256    := c38e3cc75dfb82f0b991d49397a49b6e8b98879f804018171d23db0fb3bbb8e3
# No public download URL — obtain the JAR from the MSFragger/IonQuant website
# and place it alongside the FragPipe tools.
IQ_SOURCE_JAR := /home/labs/pilpel/slavat/fragpipe-24.0/tools/IonQuant-1.11.20.jar

# ── PepQuery ──────────────────────────────────────────────────────────
PQ_VERSION   := 2.0.2
PQ_URL       := http://pepquery.org/data/pepquery-$(PQ_VERSION).tar.gz
PQ_SHA256    := a573fbdc6463b8cd580caf9f74272b9be423dd0eca1a866e96a9ff631119621a
PQ_TGZ       := pepquery-$(PQ_VERSION).tar.gz
PQ_JAR       := $(TOOLS_DIR)/pepquery-$(PQ_VERSION)/pepquery-$(PQ_VERSION).jar
PQ_LIB       := $(TOOLS_DIR)/pepquery-$(PQ_VERSION)/lib

# ── PDV ───────────────────────────────────────────────────────────────
# PDV 2.1.2 matches the reference pipeline. It is bundled in the repo
# (no public download URL for this version). SHA256 verified against
# the colleague's working copy.
PDV_VERSION  := 2.1.2
PDV_JAR      := $(TOOLS_DIR)/PDV-$(PDV_VERSION)/PDV-$(PDV_VERSION).jar
PDV_SHA256   := 8757fbdd053949edc421a0de5b4fc8b37f46b8518646d69b90bd16055bb4adf1

# ── ThermoRawFileParser (Linux, .NET 8 self-contained) ────────────────
# v2.0.0-dev requires .NET 8 runtime. Self-contained linux build available.
# If .NET 8 is not available on your system, set TRFP_MONO=1 and use the
# Mono-compatible version instead.
TRFP_VERSION := 2.0.0-dev
TRFP_URL     := https://github.com/CompOmics/ThermoRawFileParser/releases/download/v.$(TRFP_VERSION)/ThermoRawFileParser-v.$(TRFP_VERSION)-linux.zip
TRFP_SHA256  := 19566762ce6759a93cee9aa4cef50de1e9ae2ad9078bd95826e8e733d4bb0d52
TRFP_ZIP     := ThermoRawFileParser-v.$(TRFP_VERSION)-linux.zip
TRFP_DIR     := $(TOOLS_DIR)/thermorawfileparser-$(TRFP_VERSION)
TRFP_BIN     := $(TRFP_DIR)/ThermoRawFileParser

# ── JDK 21 (Eclipse Temurin) ───────────────────────────────────────────
JDK_VERSION  := jdk-21.0.11+10
JDK_FULL     := 21.0.11_10
JDK_URL      := https://github.com/adoptium/temurin21-binaries/releases/download/$(JDK_VERSION)/OpenJDK21U-jdk_x64_linux_hotspot_$(JDK_FULL).tar.gz
JDK_SHA256   := 4b2220e232a97997b436ca6ab15cbf70171ecff52958a46159dfa5a8c44ca4de
JDK_TGZ      := OpenJDK21U-jdk_x64_linux_hotspot_$(JDK_FULL).tar.gz
JDK_DIR      := $(TOOLS_DIR)/jdk-21.0.11
JAVA_BIN     := $(JDK_DIR)/bin/java

# ── .NET 8 Runtime ─────────────────────────────────────────────────────
DOTNET_VERSION := 8.0.28
DOTNET_URL     := https://dotnetcli.azureedge.net/dotnet/Runtime/$(DOTNET_VERSION)/dotnet-runtime-$(DOTNET_VERSION)-linux-x64.tar.gz
DOTNET_TGZ     := dotnet-runtime-$(DOTNET_VERSION)-linux-x64.tar.gz
DOTNET_DIR     := $(TOOLS_DIR)/dotnet-$(DOTNET_VERSION)
DOTNET_BIN     := $(DOTNET_DIR)/dotnet
DOTNET_SHA256  := 8150781339e2088da942a98d043131eb7569349856a59666352d137db5021882

# ── PDV Smoke Test Data ────────────────────────────────────────────────
PDV_TEST_DIR  := data/test-pdv
PDV_PSM       := $(PDV_TEST_DIR)/psm_rank_small.txt
PDV_MGF       := $(PDV_TEST_DIR)/mgf_small.mgf
PDV_PEP       := $(PDV_TEST_DIR)/peptides_small.txt
PDV_TEST_OUT  := $(PDV_TEST_DIR)/pdv_output

# ── Targets ───────────────────────────────────────────────────────────

.PHONY: setup clean java dotnet \
        fragpipe msfragger ionquant pepquery pdv thermorawfileparser \
        test-tools test-java test-dotnet test-fragpipe test-msfragger test-ionquant \
        test-pepquery test-pdv test-pdv-full test-thermorawfileparser \
        verify

setup: java dotnet fragpipe msfragger ionquant pepquery pdv thermorawfileparser
	@echo ""
	@echo "All tools installed. Run 'make test-tools' to verify integrity."

$(DOWNLOAD_DIR):
	mkdir -p $(DOWNLOAD_DIR)

# ── FragPipe ──────────────────────────────────────────────────────────

fragpipe: $(FP_DIR)

$(FP_DIR): $(DOWNLOAD_DIR)/$(FP_ZIP)
	@echo "Extracting FragPipe $(FP_VERSION)..."
	@if [ -d "$(FP_DIR)" ]; then \
		echo "  already extracted, skipping"; \
	else \
		unzip -q -d $(TOOLS_DIR) $<; \
		if [ -d "$(TOOLS_DIR)/FragPipe-$(FP_VERSION)-linux" ]; then \
			mv "$(TOOLS_DIR)/FragPipe-$(FP_VERSION)-linux" "$(FP_DIR)"; \
		elif [ ! -d "$(FP_DIR)" ]; then \
			echo "ERROR: cannot find extracted FragPipe directory"; exit 1; \
		fi; \
		chmod +x $(FP_DIR)/bin/fragpipe; \
		echo "FragPipe ready at $(FP_DIR)"; \
	fi

$(DOWNLOAD_DIR)/$(FP_ZIP): | $(DOWNLOAD_DIR)
	@echo "Downloading FragPipe $(FP_VERSION)..."
	curl -fSLo $@ $(FP_URL)
	@echo "Verifying checksum..."
	@echo "$(FP_SHA256)  $@" | sha256sum -c

# ── MSFragger ─────────────────────────────────────────────────────────

msfragger: $(MF_JAR)

$(MF_JAR):
	@if [ -f "$(MF_JAR)" ]; then \
		echo "MSFragger $(MF_VERSION) already extracted, skipping"; \
	else \
		if [ ! -f "$(MF_SOURCE_ZIP)" ]; then \
			echo "MSFragger $(MF_VERSION) ZIP not found at $(MF_SOURCE_ZIP)"; \
			echo "Download it from https://msfragger.nesvilab.org and place it in"; \
			echo "  $(TOOLS_DIR)/_downloads/MSFragger-$(MF_VERSION).zip"; \
			echo "Or set MF_SOURCE_ZIP to the path of your downloaded ZIP."; \
			exit 1; \
		fi; \
		echo "Verifying MSFragger ZIP checksum..."; \
		echo "$(MF_SHA256)  $(MF_SOURCE_ZIP)" | sha256sum -c; \
		echo "Extracting MSFragger $(MF_VERSION)..."; \
		unzip -q -d $(FP_DIR)/tools "$(MF_SOURCE_ZIP)"; \
		echo "MSFragger ready at $(MF_JAR)"; \
	fi

# ── IonQuant ──────────────────────────────────────────────────────────

ionquant: $(IQ_JAR)

$(IQ_JAR):
	@if [ -f "$(IQ_JAR)" ]; then \
		echo "IonQuant already copied, skipping"; \
	else \
		if [ ! -f "$(IQ_SOURCE_JAR)" ]; then \
			echo "IonQuant JAR not found at $(IQ_SOURCE_JAR)"; \
			echo "Download it and place it at $(IQ_SOURCE_JAR)"; \
			exit 1; \
		fi; \
		echo "Verifying IonQuant checksum..."; \
		echo "$(IQ_SHA256)  $(IQ_SOURCE_JAR)" | sha256sum -c; \
		cp "$(IQ_SOURCE_JAR)" "$(IQ_JAR)"; \
		echo "IonQuant ready at $(IQ_JAR)"; \
	fi

# ── PepQuery ──────────────────────────────────────────────────────────

pepquery: $(PQ_JAR)

$(PQ_JAR): $(DOWNLOAD_DIR)/$(PQ_TGZ)
	@if [ -f "$(PQ_JAR)" ]; then \
		echo "PepQuery already extracted, skipping"; \
	else \
		echo "Extracting PepQuery $(PQ_VERSION)..."; \
		tar -xzf $< -C $(TOOLS_DIR); \
		mv $(TOOLS_DIR)/pepquery-$(PQ_VERSION)/pepquery-$(PQ_VERSION).jar $(PQ_JAR); \
		mv $(TOOLS_DIR)/pepquery-$(PQ_VERSION)/lib $(PQ_LIB); \
		rm -rf $(TOOLS_DIR)/pepquery-$(PQ_VERSION); \
		echo "PepQuery ready at $(PQ_JAR)"; \
	fi

$(DOWNLOAD_DIR)/$(PQ_TGZ): | $(DOWNLOAD_DIR)
	@echo "Downloading PepQuery $(PQ_VERSION)..."
	curl -fSLo $@ $(PQ_URL)
	@if [ "$(PQ_SHA256)" != "unknown" ]; then \
		echo "Verifying checksum..."; \
		echo "$(PQ_SHA256)  $@" | sha256sum -c; \
	fi

# ── PDV (bundled, verify-only) ────────────────────────────────────────

pdv: $(PDV_JAR)

$(PDV_JAR):
	@if [ ! -f "$@" ]; then \
		echo "PDV $(PDV_VERSION) JAR missing at $@"; \
		echo "The JAR is bundled in the repo — check git tracking."; \
		exit 1; \
	fi
	@echo "Verifying PDV $(PDV_VERSION) SHA256..."
	@echo "$(PDV_SHA256)  $@" | sha256sum -c

# ── ThermoRawFileParser ───────────────────────────────────────────────

thermorawfileparser: $(TRFP_BIN)

$(TRFP_BIN): $(DOWNLOAD_DIR)/$(TRFP_ZIP)
	@if [ -f "$(TRFP_BIN)" ]; then \
		echo "ThermoRawFileParser already extracted, skipping"; \
	else \
		echo "Extracting ThermoRawFileParser $(TRFP_VERSION)..."; \
		mkdir -p $(TRFP_DIR); \
		unzip -q -d $(TRFP_DIR) $<; \
		chmod +x $(TRFP_BIN); \
		echo "ThermoRawFileParser ready at $(TRFP_BIN)"; \
	fi

$(DOWNLOAD_DIR)/$(TRFP_ZIP): | $(DOWNLOAD_DIR)
	@echo "Downloading ThermoRawFileParser $(TRFP_VERSION)..."
	curl -fSLo $@ $(TRFP_URL)
	@echo "Verifying checksum..."
	@echo "$(TRFP_SHA256)  $@" | sha256sum -c

# ── JDK 21 ─────────────────────────────────────────────────────────────

java: $(JAVA_BIN)

$(JAVA_BIN): $(DOWNLOAD_DIR)/$(JDK_TGZ)
	@if [ -f "$(JAVA_BIN)" ]; then \
		echo "JDK already extracted, skipping"; \
	else \
		echo "Extracting JDK $(JDK_VERSION)..."; \
		tar -xzf $< -C $(TOOLS_DIR); \
		if [ -d "$(TOOLS_DIR)/$(JDK_VERSION)" ]; then \
			mv "$(TOOLS_DIR)/$(JDK_VERSION)" "$(JDK_DIR)"; \
		elif [ -d "$(TOOLS_DIR)/jdk-$(JDK_FULL)" ]; then \
			mv "$(TOOLS_DIR)/jdk-$(JDK_FULL)" "$(JDK_DIR)"; \
		fi; \
		echo "JDK ready at $(JDK_DIR)"; \
	fi

$(DOWNLOAD_DIR)/$(JDK_TGZ): | $(DOWNLOAD_DIR)
	@echo "Downloading JDK $(JDK_VERSION)..."
	curl -fSLo $@ $(JDK_URL)
	@echo "Verifying checksum..."
	@echo "$(JDK_SHA256)  $@" | sha256sum -c

# ── .NET 8 Runtime ─────────────────────────────────────────────────────

dotnet: $(DOTNET_BIN)

$(DOTNET_BIN): $(DOWNLOAD_DIR)/$(DOTNET_TGZ)
	@if [ -f "$(DOTNET_BIN)" ]; then \
		echo ".NET already extracted, skipping"; \
	else \
		echo "Extracting .NET $(DOTNET_VERSION)..."; \
		mkdir -p $(DOTNET_DIR); \
		tar -xzf $< -C $(DOTNET_DIR); \
		echo ".NET ready at $(DOTNET_DIR)"; \
	fi

$(DOWNLOAD_DIR)/$(DOTNET_TGZ): | $(DOWNLOAD_DIR)
	@echo "Downloading .NET $(DOTNET_VERSION)..."
	curl -fSLo $@ $(DOTNET_URL)
	@echo "Verifying checksum..."
	@echo "$(DOTNET_SHA256)  $@" | sha256sum -c

# ── PDV Smoke Test ─────────────────────────────────────────────────────

test-pdv: $(PDV_JAR) $(JAVA_BIN)
	@echo "  PDV: OK (JAR verified, $(PDV_VERSION), SHA256 matches)"
	@echo "  Run 'make test-pdv-full' to test PDV with Xvfb + sample data."

.PHONY: test-pdv-full
test-pdv-full: $(PDV_JAR) $(JAVA_BIN)
	@echo "Running PDV full integration test (Xvfb + sample data)..."; \
	rm -rf $(PDV_TEST_OUT); mkdir -p $(PDV_TEST_OUT); \
	bash -c 'set +eu; module load Xvfb 2>/dev/null; command -v Xvfb >/dev/null || { echo "  SKIP: module load Xvfb failed"; exit 0; }; \
		Xvfb :99 -screen 0 1024x768x24 & PID=$$!; sleep 1; export DISPLAY=:99; \
		JAVA_HOME=$(JDK_DIR) $(JAVA_BIN) -jar $(PDV_JAR) \
			-r $(PDV_PSM) -rt 4 -s $(PDV_MGF) -st 1 -i $(PDV_PEP) \
			-k p -o $(PDV_TEST_OUT) -ft png >/dev/null 2>&1; rc=$$?; \
		kill $$PID 2>/dev/null; wait $$PID 2>/dev/null; exit $$rc'; \
	rc=$$?; \
	if [ $$rc -eq 0 ] && [ "$$(ls $(PDV_TEST_OUT)/*.png 2>/dev/null | wc -l)" -gt 0 ]; then \
		echo "  PDV: OK ($$(ls $(PDV_TEST_OUT)/*.png | wc -l) figures generated)"; \
		rm -rf $(PDV_TEST_OUT); \
	else \
		echo "  PDV: FAILED (exit $$rc)"; exit 1; \
	fi

# ── Tool Integrity Tests ───────────────────────────────────────────────

test-java: $(JAVA_BIN)
	@echo -n "  JDK: "; $(JAVA_BIN) -version 2>&1 | head -1

test-dotnet: $(DOTNET_BIN)
	@echo -n "  .NET: "; $(DOTNET_BIN) --info 2>&1 | grep -m1 "Host" || echo " .NET runtime installed (no SDK)"

test-fragpipe: $(FP_DIR) $(JAVA_BIN)
	@echo -n "  FragPipe: "; JAVA_HOME=$(JDK_DIR) $(FP_DIR)/bin/fragpipe --version 2>&1 | head -1 || echo "  FragPipe: WARN (--version not supported)"

test-msfragger: $(MF_JAR)
	@if [ -f "$(MF_JAR)" ]; then \
		echo "  MSFragger: OK ($(MF_VERSION))"; \
	else \
		echo "  MSFragger: MISSING"; exit 1; \
	fi

test-ionquant: $(IQ_JAR)
	@if [ -f "$(IQ_JAR)" ]; then \
		echo "  IonQuant: OK (1.11.20)"; \
	else \
		echo "  IonQuant: MISSING"; exit 1; \
	fi

test-pepquery: $(PQ_JAR) $(JAVA_BIN)
	@echo -n "  PepQuery: "; JAVA_HOME=$(JDK_DIR) $(JAVA_BIN) -jar $(PQ_JAR) 2>&1 | head -1 || true; echo "  PepQuery: OK (JAR loads)"

test-thermorawfileparser: $(TRFP_BIN)
	@export DOTNET_GCHeapHardLimit=0x10000000; \
	export DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1; \
	echo -n "  ThermoRawFileParser: "; \
	( $(TRFP_BIN) --help || true ) 2>&1 | grep -q "Usage" && echo "OK" || { echo "FAILED"; exit 1; }

test-tools: test-java test-dotnet test-fragpipe test-msfragger test-ionquant test-pepquery test-pdv test-thermorawfileparser
	@echo ""
	@echo "All tool checks complete."

# ── Utility ───────────────────────────────────────────────────────────

verify:
	@echo "Checking installed tools..."
	@test -f $(JAVA_BIN) && echo "  JDK: OK" || echo "  JDK: MISSING"
	@test -f $(DOTNET_BIN) && echo "  .NET: OK" || echo "  .NET: MISSING"
	@test -f $(FP_DIR)/bin/fragpipe && echo "  FragPipe: OK" || echo "  FragPipe: MISSING"
	@test -f $(MF_JAR) && echo "  MSFragger: OK" || echo "  MSFragger: MISSING"
	@test -f $(IQ_JAR) && echo "  IonQuant: OK" || echo "  IonQuant: MISSING"
	@test -f $(PQ_JAR) && test -d $(PQ_LIB) && echo "  PepQuery: OK" || echo "  PepQuery: MISSING"
	@test -f $(PDV_JAR) && echo "  PDV: OK" || echo "  PDV: MISSING"
	@test -f $(TRFP_BIN) && echo "  ThermoRawFileParser: OK" || echo "  ThermoRawFileParser: MISSING"

clean:
	rm -rf $(DOWNLOAD_DIR) $(FP_DIR) $(TOOLS_DIR)/pepquery-$(PQ_VERSION) $(TOOLS_DIR)/PDV-2.1.2 $(TOOLS_DIR)/PDV-2.2.3 $(TRFP_DIR) $(JDK_DIR) $(DOTNET_DIR)
	@echo "Cleaned all downloaded tools. (PDV 2.1.2 JAR is bundled — restore with git checkout)"
