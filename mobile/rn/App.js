import React, { useEffect, useState } from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { ActivityIndicator, View } from 'react-native';
import { supabase } from './src/config/supabaseConfig';

// Pantallas
import LoginScreen from './src/screens/LoginScreen';
import OTListScreen from './src/screens/OTListScreen';
import OTDetailScreen from './src/screens/OTDetailScreen';
import ExecutionScreen from './src/screens/ExecutionScreen';
import ClosureScreen from './src/screens/ClosureScreen';

const Stack = createNativeStackNavigator();

export default function App() {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Check if user is already logged in
    const checkUser = async () => {
      try {
        const { data: { user } } = await supabase.auth.getUser();
        setUser(user);
      } catch (error) {
        console.error('Error checking user:', error);
      } finally {
        setLoading(false);
      }
    };

    checkUser();

    // Listen to auth changes
    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      (event, session) => {
        setUser(session?.user || null);
      }
    );

    return () => subscription?.unsubscribe();
  }, []);

  if (loading) {
    return (
      <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center' }}>
        <ActivityIndicator size="large" color="#1e3c72" />
      </View>
    );
  }

  return (
    <NavigationContainer>
      <Stack.Navigator
        screenOptions={{
          headerShown: false,
          animationEnabled: true,
        }}
      >
        {!user && (
          <Stack.Screen
            name="Login"
            component={LoginScreen}
            options={{ animationTypeForReplace: 'pop' }}
          />
        )}
        {user && (
          <>
            <Stack.Screen
              name="OTList"
              component={OTListScreen}
              options={{ title: 'OT del Día' }}
            />
            <Stack.Screen
              name="OTDetail"
              component={OTDetailScreen}
              options={{ title: 'Detalle OT' }}
            />
            <Stack.Screen
              name="Execution"
              component={ExecutionScreen}
              options={{ title: 'Ejecución' }}
            />
            <Stack.Screen
              name="Closure"
              component={ClosureScreen}
              options={{ title: 'Cierre' }}
            />
          </>
        )}
      </Stack.Navigator>
    </NavigationContainer>
  );
}
