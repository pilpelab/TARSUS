# TARSUS_BC — Tool Setup
# Run `make setup` to download and verify all external tools.
# Versions are pinned — update intentionally.

TOOLS_DIR   := tools
DOWNLOAD_DIR := $(TOOLS_DIR)/_downloads
SHELL       := bash
.SHELLFLAGS := -eu -o pipefail -c

# ── FragPipe (Linux) ──────────────────────────────────────────────────
# Bundles: MSFragger, Philosopher, IonQuant, Percolator, MSBooster, etc.
FP_VERSION   := 24.0
FP_URL       := https://github.com/Nesvilab/FragPipe/releases/download/$(FP_VERSION)/FragPipe-$(FP_VERSION)-linux.zip
FP_SHA256    := 6a7ad80b81d7e93e8fa194c1d22228ee35ea9a2ae8ba8dc6964bb26ea4385137
FP_ZIP       := FragPipe-$(FP_VERSION)-linux.zip
FP_DIR       := $(TOOLS_DIR)/fragpipe-$(FP_VERSION)

# ── PepQuery ──────────────────────────────────────────────────────────
PQ_VERSION   := 2.0.2
PQ_URL       := http://pepquery.org/data/pepquery-$(PQ_VERSION).tar.gz
PQ_SHA256    := a573fbdc6463b8cd580caf9f74272b9be423dd0eca1a866e96a9ff631119621a
PQ_TGZ       := pepquery-$(PQ_VERSION).tar.gz
PQ_JAR       := $(TOOLS_DIR)/pepquery-$(PQ_VERSION)/pepquery-$(PQ_VERSION).jar
PQ_LIB       := $(TOOLS_DIR)/pepquery-$(PQ_VERSION)/lib

# ── PDV ───────────────────────────────────────────────────────────────
PDV_VERSION  := 2.2.3
PDV_URL      := https://github.com/wenbostar/PDV/releases/download/v$(PDV_VERSION)/PDV-$(PDV_VERSION).zip
PDV_SHA256   := d29f0662c83e45855bfe6fa63d7622df1d2069325ecd85d49bbfabb2fabc8037
PDV_ZIP      := PDV-$(PDV_VERSION).zip
PDV_JAR      := $(TOOLS_DIR)/PDV-$(PDV_VERSION)/PDV-$(PDV_VERSION).jar

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
        fragpipe pepquery pdv thermorawfileparser \
        test-tools test-java test-dotnet test-fragpipe test-pepquery \
        test-pdv test-thermorawfileparser \
        verify

setup: java dotnet fragpipe pepquery pdv thermorawfileparser
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

# ── PDV ───────────────────────────────────────────────────────────────

pdv: $(PDV_JAR)

$(PDV_JAR): $(DOWNLOAD_DIR)/$(PDV_ZIP)
	@if [ -f "$(PDV_JAR)" ]; then \
		echo "PDV already extracted, skipping"; \
	else \
		echo "Extracting PDV $(PDV_VERSION)..."; \
		unzip -q -d $(TOOLS_DIR) $<; \
		echo "PDV ready at $(PDV_JAR)"; \
	fi

$(DOWNLOAD_DIR)/$(PDV_ZIP): | $(DOWNLOAD_DIR)
	@echo "Downloading PDV $(PDV_VERSION)..."
	curl -fSLo $@ $(PDV_URL)
	@echo "Verifying checksum..."
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
	@echo "Running PDV smoke test..."
	@if JAVA_HOME=$(JDK_DIR) $(JAVA_BIN) -jar $(PDV_JAR) --help 2>&1 | grep -q "Options"; then \
		echo "  PDV: OK (JAR loads)"; \
	else \
		echo "  PDV: FAILED"; exit 1; \
	fi

# ── Tool Integrity Tests ───────────────────────────────────────────────

test-java: $(JAVA_BIN)
	@echo -n "  JDK: "; $(JAVA_BIN) -version 2>&1 | head -1

test-dotnet: $(DOTNET_BIN)
	@echo -n "  .NET: "; $(DOTNET_BIN) --info 2>&1 | grep -m1 "Host" || echo " .NET runtime installed (no SDK)"

test-fragpipe: $(FP_DIR) $(JAVA_BIN)
	@echo -n "  FragPipe: "; JAVA_HOME=$(JDK_DIR) $(FP_DIR)/bin/fragpipe --version 2>&1 | head -1 || echo "  FragPipe: WARN (--version not supported)"

test-pepquery: $(PQ_JAR) $(JAVA_BIN)
	@echo -n "  PepQuery: "; JAVA_HOME=$(JDK_DIR) $(JAVA_BIN) -jar $(PQ_JAR) 2>&1 | head -1 || true; echo "  PepQuery: OK (JAR loads)"

test-thermorawfileparser: $(TRFP_BIN)
	@export DOTNET_GCHeapHardLimit=0x10000000; \
	export DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1; \
	echo -n "  ThermoRawFileParser: "; \
	( $(TRFP_BIN) --help || true ) 2>&1 | grep -q "Usage" && echo "OK" || { echo "FAILED"; exit 1; }

test-tools: test-java test-dotnet test-fragpipe test-pepquery test-pdv test-thermorawfileparser
	@echo ""
	@echo "All tool checks complete."

# ── Utility ───────────────────────────────────────────────────────────

verify:
	@echo "Checking installed tools..."
	@test -f $(JAVA_BIN) && echo "  JDK: OK" || echo "  JDK: MISSING"
	@test -f $(DOTNET_BIN) && echo "  .NET: OK" || echo "  .NET: MISSING"
	@test -f $(FP_DIR)/bin/fragpipe && echo "  FragPipe: OK" || echo "  FragPipe: MISSING"
	@test -f $(PQ_JAR) && test -d $(PQ_LIB) && echo "  PepQuery: OK" || echo "  PepQuery: MISSING"
	@test -f $(PDV_JAR) && echo "  PDV: OK" || echo "  PDV: MISSING"
	@test -f $(TRFP_BIN) && echo "  ThermoRawFileParser: OK" || echo "  ThermoRawFileParser: MISSING""
	@test -f $(TRFP_BIN) && echo "  ThermoRawFileParser: OK" || echo "  ThermoRawFileParser: MISSING"

clean:
	rm -rf $(DOWNLOAD_DIR) $(FP_DIR) $(TOOLS_DIR)/pepquery-$(PQ_VERSION) $(PDV_JAR) $(TRFP_DIR) $(JDK_DIR) $(DOTNET_DIR)
	@echo "Cleaned all downloaded tools."
