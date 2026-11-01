import { KeychainAccess, SecureStorage } from "@aparajita/capacitor-secure-storage";
import type { Vault } from "./tokens";

/**
 * The Keychain (iOS) and Keystore-encrypted storage (Android). Items stay on this device: a backup restored on
 * another phone carries neither the refresh token nor the device id, so it signs in as a new device.
 */
export async function openVault(): Promise<Vault> {
  await SecureStorage.setDefaultKeychainAccess(KeychainAccess.whenUnlockedThisDeviceOnly);
  await SecureStorage.setSynchronize(false);
  return {
    get: (key) => SecureStorage.getItem(key),
    set: (key, value) => SecureStorage.setItem(key, value),
    remove: async (key) => {
      await SecureStorage.removeItem(key);
    },
  };
}
