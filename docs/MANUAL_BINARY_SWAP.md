# Manual binary swap (Text file busy workaround)

When `scripts/install.sh` cannot replace the running jcode binary
(`cp: Text file busy` because the running process has the file mapped
into its address space), the binary can be swapped manually without
killing the running session:

```bash
# 1. Move old binary aside (does not touch mmap pages — running
#    process keeps its existing pages via open fd)
mv /home/leroy/.jcode/builds/versions/0.65.0/jcode \
   /home/leroy/.jcode/builds/versions/0.65.0/jcode.old

# 2. Copy canary binary into place (target path is now unlinked,
#    so cp succeeds)
cp /home/leroy/.local/bin/jcode-canary \
   /home/leroy/.jcode/builds/versions/0.65.0/jcode

# 3. Verify hash matches
md5sum /home/leroy/.jcode/builds/versions/0.65.0/jcode \
       /home/leroy/.local/bin/jcode-canary
```

Result: the running session keeps its mapped pages and continues
uninterrupted; new jcode invocations get the canary binary (with
the swarm-coordinator-first patch applied).

The install.sh `cp` failure is benign for the running session — the
next `jcode` invocation picks up the canary naturally once the build
target has been replaced by either install.sh or this manual procedure.