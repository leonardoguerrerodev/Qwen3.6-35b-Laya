read /run/media/xaski/7c0ba586-7758-4419-b3de-f524b9c9a1fb/!GitHub/!Obsedium/Qwen3.6-35b+Laya/setup/qwen-setup.sh:1-50


 Now I have a clear picture. Let me create the plan.md file with a comprehensive action plan.

 The situation:
 1. qwen-setup.sh copies laya/ files from the repo to ~/.local/share/qwen/laya/
 2. qwen-setup.sh generates ~/.qwen-local.sh from a heredoc
 3. qwen-setup.sh generates qwen-menu.py from a heredoc
 4. The user wants to use symlinks instead of copies/generations

 My plan:
 1. Create qwen-local.sh in the repo (extract from the heredoc in setup script)


 2. Create qwen-menu.py in the repo (extract from the heredoc in setup script)

 3. Update qwen-setup.sh to use symlinks instead of copying/generating

 4. Replace the current files with symlinks

 The tricky part is that ~/.qwen-local.sh has a dynamically appended QWEN_PI_DIR_DEFAULT line at the end, so I'll need to handle that carefully when
 creating the template and updating the setup script.

 For the implementation, I'm going to create template files in the repo without that final line, then have the setup script create symlinks and append the
 dynamic content. The setup script also needs to locate the repo path to set up the symlinks correctly, so I'll add a find_repo() function that searches
 for the repo directory.

 The key challenge is that the setup script runs from different locations depending on how it's invoked, so I need a reliable way to detect where the repo
 actually lives. I'm considering a few approaches: checking if we're already in the repo, traversing up the directory tree to find the setup directory, or
 searching known paths. Each has tradeoffs in complexity versus reliability.

 The cleanest solution is to have the setup script detect the repo location first, then use that path to create symlinks for the template files, and
 finally append the dynamic QWEN_PI_DIR_DEFAULT line to the symlinked file. The venvs stay in ~/.local/share/qwen/ since they're user-specific and
 shouldn't live in the repo.
