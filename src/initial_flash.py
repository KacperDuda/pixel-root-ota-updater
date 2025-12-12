import subprocess
import sys
import os
import argparse

"""
Skrypt do PIERWSZEGO wgrania systemu z własnymi kluczami.
Wymaga: 
1. Zainstalowanego 'adb' i 'fastboot' w PATH.
2. Telefonu w trybie Bootloader.
3. Odblokowanego bootloadera (OEM Unlocking).
4. Pobranej paczki ZIP z Twojego Cloud Storage.
5. Pobraniu klucza publicznego avb_pkmd.bin (wygenerowanego przez avbroot).
"""

def run_cmd(command):
    print(f"EXEC: {command}")
    try:
        subprocess.check_call(command, shell=True)
    except subprocess.CalledProcessError:
        print("Błąd podczas wykonywania komendy. Przerywam.")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Flashowanie Pixel 10 (Frankel) z custom AVB.")
    parser.add_argument("--zip", required=True, help="Ścieżka do spatchowanego pliku OTA .zip")
    parser.add_argument("--key", required=True, help="Ścieżka do klucza publicznego avb_pkmd.bin")
    
    args = parser.parse_args()

    print("!!! OSTRZEŻENIE !!!")
    print("Ten proces wymaże WSZYSTKIE dane na telefonie (factory reset).")
    print("Telefon musi mieć odblokowany bootloader.")
    confirm = input("Czy chcesz kontynuować? (wpisz 'TAK'): ")
    
    if confirm != "TAK":
        print("Anulowano.")
        return

    # 1. Wgranie klucza niestandardowego AVB
    print("\n--- Krok 1: Wgrywanie klucza AVB ---")
    run_cmd(f"fastboot flash avb_custom_key {args.key}")
    
    # 2. Flashowanie systemu (update -w wymusza wipe)
    # 'fastboot update' działa idealnie z plikami OTA zip, obsługuje partycje dynamiczne
    print("\n--- Krok 2: Flashowanie systemu ---")
    run_cmd(f"fastboot update -w {args.zip}")

    print("\n--- SUKCES ---")
    print("Telefon zrestartuje się teraz.")
    print("Po konfiguracji:")
    print("1. Zrestartuj ponownie do bootloadera.")
    print("2. Wykonaj: 'fastboot flashing lock'.")
    print("3. Zatwierdź na ekranie telefonu (potwierdź custom OS).")
    print("4. Zainstaluj aplikację Custota i KernelSU Next Manager.")

if __name__ == "__main__":
    main()