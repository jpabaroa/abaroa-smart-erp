import { createClient } from '@supabase/supabase-js';
import * as SecureStore from 'expo-secure-store';

const SUPABASE_URL = 'https://uupvfuqwjxqagrmpxrzp.supabase.co';
const SUPABASE_ANON_KEY = 'sb_publishable_L1xcwujIXYVXNnTHKB1VaQ_zy_cEmmz';

export const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
  auth: {
    storage: SecureStore,
    autoRefreshToken: true,
    persistSession: true,
    detectSessionInUrl: false,
  },
});
