import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import {
  checkContractVersion,
  RUN_CONFIG_CONTRACT_VERSION,
  ACTIONS_SCHEMA_VERSION,
  PROFILE_SCHEMA_VERSION,
  _resetWarnMemo,
} from "./contract-version.js";

describe("checkContractVersion", () => {
  let warnSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    _resetWarnMemo();
    warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
  });

  afterEach(() => {
    warnSpy.mockRestore();
  });

  it("returns true and is silent when declared equals knownMax", () => {
    const ok = checkContractVersion({
      artefact: "shipwright_run_config.json",
      path: "/foo/run.json",
      declared: 1,
      knownMax: 1,
    });
    expect(ok).toBe(true);
    expect(warnSpy).not.toHaveBeenCalled();
  });

  it("returns true and is silent when declared is missing (undefined)", () => {
    const ok = checkContractVersion({
      artefact: "shipwright_run_config.json",
      path: "/foo/run.json",
      declared: undefined,
      knownMax: 1,
    });
    expect(ok).toBe(true);
    expect(warnSpy).not.toHaveBeenCalled();
  });

  it("returns true and is silent when declared is null (pre-versioning files)", () => {
    const ok = checkContractVersion({
      artefact: "shipwright_run_config.json",
      path: "/foo/run.json",
      declared: null,
      knownMax: 1,
    });
    expect(ok).toBe(true);
    expect(warnSpy).not.toHaveBeenCalled();
  });

  it("warns (and returns false) when declared exceeds knownMax", () => {
    const ok = checkContractVersion({
      artefact: "shipwright_run_config.json",
      path: "/foo/run.json",
      declared: 2,
      knownMax: 1,
    });
    expect(ok).toBe(false);
    expect(warnSpy).toHaveBeenCalledTimes(1);
    const payload = JSON.parse(warnSpy.mock.calls[0][0] as string);
    expect(payload.event).toBe("contract_version_ahead");
    expect(payload.declared).toBe(2);
    expect(payload.knownMax).toBe(1);
  });

  it("warns once per (artefact, path, version) triple — second identical call is silent", () => {
    checkContractVersion({
      artefact: "shipwright_run_config.json",
      path: "/foo/run.json",
      declared: 99,
      knownMax: 1,
    });
    checkContractVersion({
      artefact: "shipwright_run_config.json",
      path: "/foo/run.json",
      declared: 99,
      knownMax: 1,
    });
    expect(warnSpy).toHaveBeenCalledTimes(1);
  });

  it("warns again for a different path with the same version", () => {
    checkContractVersion({
      artefact: "shipwright_run_config.json",
      path: "/foo/a.json",
      declared: 99,
      knownMax: 1,
    });
    checkContractVersion({
      artefact: "shipwright_run_config.json",
      path: "/foo/b.json",
      declared: 99,
      knownMax: 1,
    });
    expect(warnSpy).toHaveBeenCalledTimes(2);
  });

  it("warns (and returns false) when declared is a non-integer number", () => {
    const ok = checkContractVersion({
      artefact: "x",
      path: "/x.json",
      declared: 1.5,
      knownMax: 1,
    });
    expect(ok).toBe(false);
    const payload = JSON.parse(warnSpy.mock.calls[0][0] as string);
    expect(payload.event).toBe("contract_version_malformed");
  });

  it("warns (and returns false) when declared is a string", () => {
    const ok = checkContractVersion({
      artefact: "x",
      path: "/x.json",
      declared: "1",
      knownMax: 1,
    });
    expect(ok).toBe(false);
    const payload = JSON.parse(warnSpy.mock.calls[0][0] as string);
    expect(payload.event).toBe("contract_version_malformed");
  });

  it("honours fieldName override in warning payload", () => {
    checkContractVersion({
      artefact: ".webui/actions.json",
      path: "/p/.webui/actions.json",
      declared: 42,
      knownMax: 1,
      fieldName: "schemaVersion",
    });
    const payload = JSON.parse(warnSpy.mock.calls[0][0] as string);
    expect(payload.field).toBe("schemaVersion");
  });
});

describe("contract version constants", () => {
  it("run-config contract version is a positive integer", () => {
    expect(Number.isInteger(RUN_CONFIG_CONTRACT_VERSION)).toBe(true);
    expect(RUN_CONFIG_CONTRACT_VERSION).toBeGreaterThan(0);
  });

  it("actions schema version is a positive integer", () => {
    expect(Number.isInteger(ACTIONS_SCHEMA_VERSION)).toBe(true);
    expect(ACTIONS_SCHEMA_VERSION).toBeGreaterThan(0);
  });

  it("profile schema version is a positive integer", () => {
    expect(Number.isInteger(PROFILE_SCHEMA_VERSION)).toBe(true);
    expect(PROFILE_SCHEMA_VERSION).toBeGreaterThan(0);
  });
});
