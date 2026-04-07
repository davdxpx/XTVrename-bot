import os

with open("README.md", "a") as f:
    f.write("\n\n## Recent Changes\n")
    f.write("- **Admin Menu Redesign:** The 'Configure Features' menu is now beautifully grouped into 'Account Perks', 'Media Tools', and 'Privacy'.\n")
    f.write("- **4GB Access Toggle:** The 'XTV Pro 4GB Access' is now a cascading per-plan feature toggle instead of a global setting.\n")
    f.write("- **Privacy Menu Access:** The Privacy Settings menu in `/myfiles` is dynamically hidden for users without the feature enabled, keeping the UI clean.\n")
    f.write("- **Automated Batch Sharing:** Batch processing now automatically generates an elegant share link summary, gated by the 'batch_sharing' plan feature.\n")
